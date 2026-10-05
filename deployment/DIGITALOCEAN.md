# Public chatbot on DigitalOcean App Platform

Deploy the existing browser frontend, Python RAG backend and company Chroma index
as one Docker web service. Public visitors do not need to sign in. The existing
models are accessed through OpenAI APIs; no model training or GPU is required.

## Deployment settings

| Setting | Value |
| --- | --- |
| Product | DigitalOcean App Platform |
| Region | Singapore (`sgp`) |
| Component | Web service named `chatbot` |
| Source | Private GitHub repository, `main` branch |
| Build | Repository-root `Dockerfile` |
| HTTP port / `PORT` | `8080` |
| Instance | `apps-s-1vcpu-2gb`: 1 shared CPU, 2 GiB RAM |
| Instance count | 1 |
| Health check | `/api/health` |
| Public route | `/`, preserving request paths |
| Automatic deployment on push | Disabled |

DigitalOcean lists this instance at **$25/month**, with 200 GiB/month bandwidth
included. OpenAI API usage and any other billable usage are separate. Review
current pricing before creating the app:
https://docs.digitalocean.com/products/app-platform/details/pricing/

The prepared specification is `.do/app.yaml`. Its repository is a placeholder
until you select your private source repository. Its API key is intentionally
empty; set the actual key in DigitalOcean's encrypted runtime environment field.

## Prepare the upload folder

From the original project directory in PowerShell:

```powershell
& ".\rag-eval-project\Scripts\python.exe" -B deployment/package.py --platform digitalocean
```

The command creates a folder and ZIP under `deployment/artifacts/`. It includes
the app, `.do/app.yaml`, all 16 company `.txt` documents, and a consistent snapshot
of the existing 82-chunk Chroma index. It does not regenerate embeddings or include
`.env`, transcript `.vtt` files, backups, local environments or evaluation outputs.
Run packaging when no ingestion or re-index job is writing to the index.

Use the **generated folder** as the root of a new **private GitHub repository**.
Commit all files, including `.do/app.yaml` and `chroma_store`. The generated
folder's `.gitignore` deliberately allows that index; the original project's
`.gitignore` excludes it. The chatbot can be public while the source repository
remains private.

Replace `YOUR_GITHUB_OWNER/YOUR_PRIVATE_REPOSITORY` in `.do/app.yaml` with the
actual `owner/repository`, and set the branch if it is not `main`. This spec is a
deployment template, not an already-created DigitalOcean app.

## Create the app in the DigitalOcean dashboard

1. Open https://cloud.digitalocean.com/apps and choose **Create App**.
2. Choose GitHub as the source, authorize access to the private repository,
   select the repository and branch, and use the repository root as the source.
3. Check that DigitalOcean detects the `Dockerfile` and a **Web Service**. The
   Dockerfile's default Gunicorn command starts both the frontend and API; no
   separate frontend hosting or build command is needed.
4. Apply the settings in the table above: Singapore, one 2 GiB instance,
   HTTP port `8080`, and health-check path `/api/health`.
5. Add component environment variables:
   - `PORT`: `8080`, runtime only.
   - `CHAT_REQUESTS_PER_MINUTE`: `30`, runtime only.
   - `OPENAI_API_KEY`: your existing key, **runtime only**, with **Encrypt** enabled.
     Enter this through DigitalOcean's environment editor, not the source spec.
6. Review the monthly charge and create the app. Wait for the Docker build,
   reranker download and health checks to succeed.
7. Open the live HTTPS address displayed by DigitalOcean and share that URL.

The dashboard settings do not automatically come from `.do/app.yaml` when you
create an app by selecting a repository. Use the table above, or apply an app
spec through DigitalOcean's spec editor or authenticated CLI. When updating an
existing app, export its current spec first and preserve the encrypted key and
repository settings; do not replace them with this template's empty placeholders.

If `doctl` is installed and already authenticated, the documented creation
command is:

```powershell
doctl apps create --spec .do/app.yaml
```

Use that command only after configuring a valid repository and the actual runtime
secret securely. Executing it creates a billable app. Dashboard creation lets you
enter the encrypted key without placing a plaintext value in a YAML file.

## Verify the deployment

At the live HTTPS URL, check `/api/health` returns `status: ok` and
`documents: 16`. Ask:

- What is MoneySign, and which personality framework is used to assess it?
- What information does the 1 View feature bring together?
- What five services does 1 Finance offer after the MoneySign assessment?

Answers should reference company `.txt` filenames. Requests for `/.env`,
`/data/moneysign_faqs.txt` and `/chroma_store/chroma.sqlite3` should return 404.
The first question loads the RAG instance; later questions reuse it.

The Docker image includes the existing company index and cached reranker.
App Platform's local filesystem is ephemeral, but each release restores its
packaged index. The chatbot does not edit its knowledge base at runtime; no
managed database, volume or re-embedding is needed for this setup. To update
knowledge, rebuild the local company index, generate a fresh package, commit it
and manually deploy that release. Runtime changes are not preserved.

One shared inference slot preserves the existing serial RAG behavior. If another
visitor is being served, the frontend shows a retry message. The global limit is
30 admitted questions per rolling minute per process. It resets on restart and
does not impose a monthly spending cap. Start with modest traffic and monitor
memory, response times and API usage before changing capacity.

The ingestion, preprocessing, chunking, embeddings, vector configuration,
retrieval, reranking, prompt, model settings and evaluation files are unchanged.

## Troubleshooting

- **Missing API key:** Add `OPENAI_API_KEY` as an encrypted runtime variable.
- **Missing company index:** Deploy the generated package and commit its
  `chroma_store`; do not upload only `src` and `web`.
- **Failed health check:** Ensure the component port and `PORT` both equal `8080`.
- **Models unavailable:** Confirm the build step downloaded the existing
  cross-encoder. Runtime uses the cached model with Hugging Face offline mode.
- **Container runs out of memory:** Review DigitalOcean's memory metrics and
  increase instance size if the actual workload requires it.

The Linux container build remains to be verified on an available Docker engine
or during the first DigitalOcean build; local API and packaging checks are not
a completed cloud deployment.

References:
https://docs.digitalocean.com/products/app-platform/how-to/create-apps/
https://docs.digitalocean.com/products/app-platform/reference/app-spec/
https://docs.digitalocean.com/products/app-platform/how-to/use-environment-variables/
https://docs.digitalocean.com/products/app-platform/details/availability/
https://docs.digitalocean.com/products/app-platform/reference/dockerfile/
