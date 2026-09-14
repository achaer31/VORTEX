"""Synthetic tests of the oracle/strict comparator, not native runtime proof."""
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from risk_fixtures import (generate,TABLES,KIND,CORE_VERSION,HARNESS_VERSION,REPO,
                           size_cases,gate_cases,campaign_cases,stop_cases)
from risk_compare import compare,ComparisonError

class RiskTools(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.reference=self.base/'reference';self.native=self.base/'simulated_output'
        self.manifest=generate(self.reference);self.native.mkdir()
        for family in TABLES:
            shutil.copyfile(self.reference/f'expected_risk_{family}_results.csv',self.native/f'risk_{family}_results.csv')
        self.metadata=dict(schema='vortex.native.risk-result.v1',fixture_kind=KIND,core_version=CORE_VERSION,
          harness_version=HARNESS_VERSION,status='COMPUTED_FOR_COMPARISON',error='',parity_evaluated='false',
          strategy_approval='false',execution_authorized='false')
        for family,meta in self.manifest['families'].items():
            self.metadata[family+'_cases']=str(meta['cases']);self.metadata[family+'_results']=str(meta['cases'])
        self.write_manifest()
    def write_manifest(self):
        with (self.native/'manifest.csv').open('w',newline='') as file:
            out=csv.writer(file);out.writerow(['key','value']);out.writerows(self.metadata.items())
    def mutate(self,family,field,value,row=0):
        path=self.native/f'risk_{family}_results.csv'
        with path.open(newline='') as file:
            reader=csv.DictReader(file);fields=reader.fieldnames;rows=list(reader)
        rows[row][field]=value
        with path.open('w',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    def test_complete_synthetic_output_passes_comparator_only(self):
        result=compare(self.reference,self.native)
        self.assertEqual(result['status'],'PARITY_PASS');self.assertGreater(result['total_cases'],120)
        self.assertEqual(result['difference_count'],0);self.assertFalse(result['execution_authorized'])
    def test_round_up_and_execution_flag_cannot_pass(self):
        self.mutate('size','lots','0.02');self.mutate('size','execution_authorized','1')
        result=compare(self.reference,self.native)
        self.assertEqual(result['status'],'PARITY_FAIL');self.assertEqual(result['difference_count'],2)
    def test_missing_not_zero_and_small_nonzero_not_zero(self):
        self.mutate('size','campaign_open_risk_after','');self.mutate('size','campaign_nominal_after','1e-14')
        result=compare(self.reference,self.native);self.assertEqual(result['difference_count'],2)
    def test_tolerance_does_not_permit_cash_budget_overrun(self):
        with (self.native/'risk_size_results.csv').open() as stream:
            rows=list(csv.DictReader(stream))
        index=next(i for i,row in enumerate(rows) if row['case_id']=='floor_exact_one_step')
        self.mutate('size','risk_cash','1.0000000001',row=index)
        with self.assertRaisesRegex(ComparisonError,'cash_budget_invariant'):compare(self.reference,self.native)
    def test_invalid_boolean_rejected(self):
        self.mutate('size','allowed','true')
        with self.assertRaisesRegex(ComparisonError,'invalid_boolean'):compare(self.reference,self.native)
    def test_nan_and_infinity_rejected(self):
        for value in ('NaN','inf','1e999'):
            self.mutate('size','risk_cash',value)
            with self.assertRaises(ComparisonError):compare(self.reference,self.native)
    def test_failed_incomplete_or_wrong_version_manifest_rejected(self):
        for key,value in [('status','FAILED'),('size_results','0'),('core_version','different'),('strategy_approval','true')]:
            original=self.metadata[key];self.metadata[key]=value;self.write_manifest()
            with self.assertRaises(ComparisonError):compare(self.reference,self.native)
            self.metadata[key]=original
    def test_missing_duplicate_or_extra_manifest_keys_rejected(self):
        del self.metadata['execution_authorized'];self.write_manifest()
        with self.assertRaises(ComparisonError):compare(self.reference,self.native)
        self.metadata['execution_authorized']='false';self.metadata['unexpected']='true';self.write_manifest()
        with self.assertRaises(ComparisonError):compare(self.reference,self.native)
        del self.metadata['unexpected'];self.write_manifest()
        with (self.native/'manifest.csv').open('a') as file:file.write('status,COMPUTED_FOR_COMPARISON\n')
        with self.assertRaises(ComparisonError):compare(self.reference,self.native)
    def test_wrong_or_missing_case_rejected(self):
        self.mutate('size','case_id','another_case')
        with self.assertRaisesRegex(ComparisonError,'case_identity'):compare(self.reference,self.native)
    def test_header_and_row_width_rejected(self):
        path=self.native/'risk_size_results.csv';path.write_text(path.read_text().replace('case_id,','case_id,extra,',1))
        with self.assertRaisesRegex(ComparisonError,'header'):compare(self.reference,self.native)
    def test_reference_file_mutation_rejected(self):
        with (self.reference/'risk_size_cases.csv').open('a') as file:file.write('\n')
        with self.assertRaisesRegex(ComparisonError,'reference_hash'):compare(self.reference,self.native)
    def test_missing_hash_entry_cannot_bypass_validation(self):
        del self.manifest['files']['risk_size_cases.csv']
        (self.reference/'risk_reference_manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ComparisonError,'reference_file_set'):compare(self.reference,self.native)
    def test_symlinked_output_rejected(self):
        path=self.native/'risk_size_results.csv';path.unlink()
        path.symlink_to(self.reference/'expected_risk_size_results.csv')
        with self.assertRaisesRegex(ComparisonError,'unsafe_file'):compare(self.reference,self.native)
    def test_fixture_coverage_and_risk_budget(self):
        sizes={row['case_id']:(row,out,kind) for row,out,kind in size_cases()}
        self.assertFalse(sizes['min_lot_no_roundup'][1]['allowed'])
        self.assertEqual(sizes['min_lot_no_roundup'][1]['lots'],0.)
        self.assertEqual(sizes['partial_004'][1]['exit_policy'],'partial_25_25_50')
        self.assertEqual(sizes['fallback_003'][1]['exit_policy'],'single_trailing')
        self.assertFalse(sizes['profile_10'][1]['execution_authorized'])
        for row,out,_ in size_cases():
            if out['allowed']:
                self.assertLessEqual(out['risk_cash'],out['budget']+1e-12)
                self.assertAlmostEqual(out['tp1_lots']+out['tp2_lots']+out['runner_lots'],out['lots'])
        campaigns={row['case_id']:out for row,out,_ in campaign_cases()}
        for side in ('long','short'):
            for level in (1,2):
                output=campaigns[f'{side}_winner_add_{level}'];self.assertTrue(output['allowed']);self.assertEqual(output['add_level'],level)
        self.assertEqual(campaigns['max_two_adds']['reason'],'add_limit_or_direction')
        self.assertEqual(campaigns['no_add_to_loser']['reason'],'loser_add_forbidden')
        self.assertEqual(campaigns['aggregate_margin_cap']['reason'],'margin')
        self.assertEqual(campaigns['consensus_outside_score_domain']['reason'],'winner_inputs_invalid')
    def test_cash_boundary_refinement_is_explicit(self):
        gates={row['case_id']:out for row,out,_ in gate_cases()}
        campaigns={row['case_id']:out for row,out,_ in campaign_cases()}
        self.assertEqual(gates['dd_boundary_90_0']['mode'],'EXTREME')
        self.assertEqual(campaigns['exact_dd_10_cash']['mode'],'FROZEN')
        self.assertEqual(campaigns['exact_dd_15_cash']['mode'],'KILL')
    def test_stop_policy_valid_both_directions_and_bad_atr(self):
        cases={row['case_id']:out for row,out,_ in stop_cases()}
        self.assertTrue(cases['long_minimum_14_atr']['allowed']);self.assertTrue(cases['short_minimum_14_atr']['allowed'])
        self.assertFalse(cases['long_cap_exceeded']['allowed']);self.assertFalse(cases['atr_missing']['allowed'])

class HarnessContract(unittest.TestCase):
    def test_complete_source_has_only_reviewed_offline_capabilities(self):
        source=(REPO/'native_mt5/VortexRiskParityCheck.mq5').read_text()
        core=(REPO/'native_mt5/VortexRiskCore.mqh').read_text()
        self.assertEqual(re.findall(r'#include\s+"([^"]+)"',source),['VortexRiskCore.mqh'])
        self.assertNotIn('#include',core)
        approved=set('ArrayResize ArraySize DoubleToString FileClose FileFlush FileIsEnding FileOpen FileReadString '
          'FileSize FileWriteArray FolderCreate GetLastError GetTickCount64 IsStopped MathAbs MathCeil MathFloor '
          'MathIsValidNumber MathMax MathMin MathRound NormalizeDouble Print ResetLastError StringFind StringFormat '
          'StringGetCharacter StringLen StringReplace StringSplit StringSubstr StringToCharArray StringToDouble'.split())
        def unreviewed(text):
            text=re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
            text=re.sub(r'"(?:\\.|[^"\\])*"','""',text)
            defined=set(re.findall(r'\b(?:void|bool|int|long|double|string)\s+([A-Za-z_]\w*)\s*\(',text))
            called=set(re.findall(r'\b([A-Za-z_]\w*)\s*\(',text))
            return called-defined-approved-{'if','for','while','return'}
        self.assertEqual(unreviewed(source+'\n'+core),set())
        self.assertEqual(unreviewed(source+'\n'+core+'\nvoid hidden(){WebRequest();}'),{'WebRequest'})
    def test_offline_default_guard_precedes_file_access(self):
        source=(REPO/'native_mt5/VortexRiskParityCheck.mq5').read_text();start=source[source.index('void OnStart()'):]
        self.assertIn('input bool EnableOfflineRiskParity=false;',source)
        self.assertLess(start.index('if(!EnableOfflineRiskParity)'),start.index('InputFile('))
        self.assertLess(start.index('FIXTURE_KIND'),start.index('FolderCreate('))
        self.assertIn('FILE_WRITE|FILE_BIN',source);self.assertIn('FileWriteArray',source);self.assertIn('FileFlush',source)
        for token in ('OrderSend(','OrderSendAsync(','AccountInfo','SymbolInfo','CopyRates(','WebRequest(','TerminalInfo','CTrade','ExpertRemove('):
            self.assertNotIn(token,source)
    def test_exact_schema_mapping_and_versions(self):
        source=(REPO/'native_mt5/VortexRiskParityCheck.mq5').read_text()
        self.assertIn(HARNESS_VERSION,source);self.assertIn(KIND,source)
        for family,(inputs,outputs) in TABLES.items():
            for fields in (inputs,outputs):self.assertIn(','.join(['case_id']+[x[0] for x in fields]),source)
        self.assertIn('MAX_RISK_CASES=512',source);self.assertIn('duplicate_case_id',source)
        self.assertIn('execution_authorized","false',source)

if __name__=='__main__':unittest.main()
