# Logistics Operations RAG Assistant

Practice assignment workspace for AeroVelo Logistics Global. The graded notebook is [`results/Logistics_Operations_RAG_Assistant_Starter.ipynb`](results/Logistics_Operations_RAG_Assistant_Starter.ipynb). The design notes are in [`docs/logistics-operations-rag-design.md`](docs/logistics-operations-rag-design.md).

Generation cells call Gemini (`gemini-3.5-flash-lite`) and need an API key. The embedding cell downloads `sentence-transformers/all-MiniLM-L6-v2` from the Hugging Face Hub and uses `HF_TOKEN` from the same file so that download is authenticated. The notebook never stores these secrets. On import it walks upward from the working directory and from the notebook folder, loads the first `.env` it finds, and reads `GOOGLE_API_KEY`. If that name is absent, it uses `GEMINI_API_KEY`. That load also puts `HF_TOKEN` into the environment for the Hub client.

## Run the notebook

Run the notebook with a project-local virtual environment named `.venv`, created at the repository root. Use that same environment as the notebook kernel.

### Create the virtual environment

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install pandas matplotlib tqdm pypdf nltk scikit-learn python-dotenv \
  langchain langchain-core langchain-community \
  langchain-text-splitters langchain-huggingface langchain-chroma \
  langchain-google-genai \
  sentence-transformers ipykernel
python -m ipykernel install --user --name=upgrad-capstone-venv --display-name="Python (.venv upgrad-capstone)"
```

Leave `.venv/` uncommitted. Recreate it with the commands above if you need a fresh environment. The commented `pip` lines in the notebook are a package list only. Install with the activated `.venv` instead of running those cells against another interpreter.

### Open the notebook and run the cells

1. Create a Gemini API key and a Hugging Face token, then save both in `.env`, using the sections below.
2. Open [`results/Logistics_Operations_RAG_Assistant_Starter.ipynb`](results/Logistics_Operations_RAG_Assistant_Starter.ipynb) in Cursor, VS Code, or Jupyter.
3. Select the kernel **Python (.venv upgrad-capstone)**. In Cursor or VS Code you can also pick the `.venv` interpreter at the repository root.
4. Run the cells from top to bottom. The import cell prints the dataset path and confirms that `GOOGLE_API_KEY` is set.
5. The first analysis run downloads NLTK English stop words if they are missing, and the embedding cell downloads `sentence-transformers/all-MiniLM-L6-v2`. Both are cached locally after that.
6. The vector-store cell deletes and recreates `chroma/logistics_rag` next to `dataset/`, then indexes the chunks. Leave that directory uncommitted.
7. From the RAG chain onward, cells call Gemini and need network access. If the import cell reports that the key is missing, fix `.env` and restart the kernel before continuing.

## Create a Gemini API key

A Gemini API key and a Google AI Studio API key are the same credential. Create it in [Google AI Studio](https://aistudio.google.com/apikey), not as a generic unrestricted Cloud key. Official reference: [Using Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key).

1. Open the [AI Studio API Keys page](https://aistudio.google.com/apikey) and sign in with a Google account.
2. Accept the Gemini API Terms of Service if this is the first time you use AI Studio.
3. Create the key:
   - New AI Studio users get a default Google Cloud project after accepting the terms. Use **Create API key** on that project.
   - If you already have Google Cloud projects, AI Studio does not list them until you import one. Open **Dashboard**, then **Projects**, choose **Import projects**, import the project, then open **API Keys** and choose **Create API key**.
4. Copy the key when AI Studio shows it. You will not be able to view the full secret again later.
5. Keys created in AI Studio on or after 28 May 2026 are authorization keys. They are restricted to the Gemini API. That is the key type this notebook should use.

If **Create API key** is disabled and the page says you do not have permission, the Cloud project is missing one of these permissions: `resourcemanager.projects.get`, `apikeys.keys.create`, `serviceusage.services.enable`, `iam.serviceAccounts.create`, or `iam.serviceAccountApiKeyBindings.create`. Ask a project admin for a role that includes them, such as Project Editor, or create a Cloud project that is not under an organization and generate the key there.

## Create a Hugging Face token

The embedding cell downloads `sentence-transformers/all-MiniLM-L6-v2` from the Hugging Face Hub. Without a token, the Hub prints:

```text
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
```

A token raises the rate limit and speeds that download. The model is public, so a **Read** token is enough. Do not create a Write token. Official reference: [User access tokens](https://huggingface.co/docs/hub/en/security-tokens).

1. Open [Access Tokens](https://huggingface.co/settings/tokens) and sign in with a Hugging Face account.
2. Choose **New token**.
3. Name it, for example `upgrad-capstone`.
4. Select the **Read** role.
5. Copy the token when the page shows it. It starts with `hf_`.

Treat this token like the Gemini key. Do not paste it into the notebook, a shell history file, or git.

## Save the keys in `.env`

Copy [`env.sample`](env.sample) to `.env` in this folder (or any parent folder up to the repository root) and replace the empty values. Do not paste the real values into the notebook, a shell history file, or git.

```text
GOOGLE_API_KEY=your-key-here
HF_TOKEN=hf_your-token-here
```

`GEMINI_API_KEY` is accepted as a fallback for the Gemini key. If both Gemini names are set, the notebook and the Gemini client use `GOOGLE_API_KEY`. This project uses `HF_TOKEN`. `HUGGING_FACE_HUB_TOKEN` is the older Hub environment name.

Restart the notebook kernel after you add or change the file, then run the import cell. It should print that `GOOGLE_API_KEY` is set, without printing the key itself. That cell loads `HF_TOKEN` into the environment before the embedding cell runs, which clears the unauthenticated Hub warning. Generation cells stop with an error if the Gemini key is still missing, or if Gemini returns HTTP 401, 403, or a quota error.
