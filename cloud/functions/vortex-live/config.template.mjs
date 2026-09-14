// Copy to a private deployment bundle as config.mjs. Never commit live values.
// Hash the UTF-8 representation of TWO DIFFERENT random 32-byte lowercase-hex tokens.
export default Object.freeze({
  ingestTokenSha256: "REPLACE_WITH_64_LOWERCASE_HEX_SHA256",
  readerTokenSha256: "REPLACE_WITH_DIFFERENT_64_LOWERCASE_HEX_SHA256",
  publicQuotes: false,
});
