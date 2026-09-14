param([Parameter(Mandatory=$true)][string]$RunPath)

# Validate only exported market-data files. No terminal or account access.
$ErrorActionPreference='Stop'
$vRun=(Resolve-Path -LiteralPath $RunPath).Path
$ci=[cultureinfo]::InvariantCulture
function VT($s){[datetime]::ParseExact($s,'yyyy-MM-ddTHH:mm:ss',$ci)}

$m=@{}
Import-Csv -LiteralPath "$vRun\manifest.csv" -Encoding UTF8 | ForEach-Object {
  $m["$($_.scope)/$($_.key)"]=$_.value
}
Write-Output ("RUN_STATUS: "+$m['export/run_status'])
$snap=VT $m['export/snapshot_server_time']
$expected='bar_open_server,timezone,symbol,timeframe,open,high,low,close,tick_volume,spread_points,real_volume'
$summary=@(foreach($tf in 'M5','M15','H1'){
  $filename=$m["$tf/filename"]
  if(!$filename -or [IO.Path]::GetFileName($filename) -cne $filename){throw "Invalid filename for $tf"}
  $file=Join-Path $vRun $filename
  $rows=@(Import-Csv -LiteralPath $file -Encoding UTF8)
  $start=VT $m["$tf/requested_start_server"]
  $end=VT $m["$tf/effective_closed_end_exclusive_server"]
  $sec=[int]$m["$tf/period_seconds"]
  $bad=0; $order=0; $prev=$null
  foreach($r in $rows){
    try {
      $t=VT $r.bar_open_server
      $o=[decimal]::Parse($r.open,$ci); $h=[decimal]::Parse($r.high,$ci)
      $l=[decimal]::Parse($r.low,$ci); $c=[decimal]::Parse($r.close,$ci)
      if($prev -and $t -le $prev){$order++}
      $prev=$t
      if($l -le 0 -or $l -gt $o -or $l -gt $c -or $h -lt $o -or $h -lt $c -or
         [long]$r.tick_volume -lt 0 -or [long]$r.real_volume -lt 0 -or [int]$r.spread_points -lt 0 -or
         $t -lt $start -or $t -ge $end -or $t.AddSeconds($sec) -gt $snap -or
         $r.symbol -cne $m['export/symbol'] -or $r.timeframe -cne $tf -or
         $r.timezone -cne 'broker_server_unknown_offset'){$bad++}
    } catch {$bad++}
  }
  $first=''; $last=''
  if($rows.Count){$first=$rows[0].bar_open_server; $last=$rows[-1].bar_open_server}
  [pscustomobject]@{
    TF=$tf; Rows=$rows.Count
    HeaderOK=((Get-Content -LiteralPath $file -Encoding UTF8 -TotalCount 1) -ceq $expected)
    ManifestOK=($rows.Count -eq [int]$m["$tf/actual_count"] -and
                $first -ceq $m["$tf/actual_first_open_server"] -and
                $last -ceq $m["$tf/actual_last_open_server"])
    First=$first; Last=$last; BadRows=$bad; OrderErrors=$order
    Status=$m["$tf/export_status"]; Incomplete=$m["$tf/history_incomplete"]
    CopyError=$m["$tf/copy_rates_error"]; Synced=$m["$tf/series_synchronized"]
    RunStatus=$m['export/run_status']
  }
})
$summary | Format-List
$summary | Export-Csv -LiteralPath "$vRun\validation-summary.csv" -NoTypeInformation -Encoding UTF8
Write-Output 'Saved validation-summary.csv. Passing checks does not verify historical completeness or execution realism.'
