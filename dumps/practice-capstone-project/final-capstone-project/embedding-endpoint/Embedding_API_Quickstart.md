# Capstone embedding API

Use the shared embedding API to turn English search queries and document chunks into vectors for retrieval.

- **Base URL** `https://103.42.50.41:1035/v1`
- **Method and route** `POST /v1/embeddings`
- **Model** `bge-small-en-v1.5`
- **Key** Use the shared embedding key from your coordinator.
- **Certificate** Save `vm02-ca.crt` in Downloads. The commands below use that exact location.

In macOS or Linux Terminal, replace `YOUR_EMBEDDINGS_KEY` and run:

```bash
curl --cacert "$HOME/Downloads/vm02-ca.crt" \
  https://103.42.50.41:1035/v1/embeddings \
  -H "Authorization: Bearer YOUR_EMBEDDINGS_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"bge-small-en-v1.5","input":["Example document chunk","Example search query"]}'
```

In Windows PowerShell, set your key and build the request body:

```powershell
$key = 'YOUR_EMBEDDINGS_KEY'
$body = @{
    model = 'bge-small-en-v1.5'
    input = @('Example document chunk', 'Example search query')
} | ConvertTo-Json -Compress
$body | curl.exe --cacert "$env:USERPROFILE\Downloads\vm02-ca.crt" `
  https://103.42.50.41:1035/v1/embeddings `
  -H "Authorization: Bearer $key" -H "Content-Type: application/json" `
  --data-binary '@-'
```

Each result in `data` contains an `index` and an `embedding` of 384 numbers. Send up to 16 texts per request and keep each chunk within 512 model tokens. Use the same model for indexing and search. If the server returns a capacity error, wait briefly and retry the batch. If you moved the certificate, use its actual file path.
