# Rozgar Saathi – Maharashtra (prototype)

A small Flask + HTML app where farmers and agricultural labourers can:

1. Search their Maharashtra district and see its employment (MGNREGA) numbers from Data.gov.in
2. Answer four Yes/No questions to see which schemes they may be eligible for
3. Use English, Hindi or Marathi, with spoken output and voice input

## Files

| File | What it does |
|---|---|
| `app.py` | Flask backend. Calls the Data.gov.in API and serves JSON to the page |
| `index.html` | The whole frontend (HTML, CSS, JavaScript) |
| `.env` | Your API key and dataset settings (private) |
| `requirements.txt` | Python packages needed |

## Run it in VS Code

1. **Install** Python 3.10+ from python.org (tick "Add Python to PATH") and VS Code with the *Python* extension.
2. **Open the folder**: VS Code → File → Open Folder → choose the folder with these files.
3. **Open a terminal**: Terminal → New Terminal.
4. **Create a virtual environment and install packages**

   Windows (PowerShell):
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   macOS / Linux:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   If VS Code asks to use the new environment, click **Yes**.
5. **Set the dataset (important).** Open `.env` and fill in `RESOURCE_ID`:
   - Go to data.gov.in, search "MGNREGA district-wise", and open a dataset that has an **API** option and columns like `state_name` and `district_name`.
   - Copy its resource ID (the long code in the API URL after `/resource/`).
   - Paste it after `RESOURCE_ID=` and save.
   - If the column names differ, change `STATE_FIELD` and `DISTRICT_FIELD` in `.env`.
6. **Start the server**: `python app.py`
7. **Open** http://127.0.0.1:5000 in Google Chrome. Press `Ctrl+C` in the terminal to stop.

To test on your phone, run with `flask run --host 0.0.0.0` (same Wi-Fi) and open `http://<your-computer-IP>:5000`. Voice input may need HTTPS on phones.

## Troubleshooting

- **"RESOURCE_ID is missing"**: complete step 5. Until then the district list uses a built-in fallback and no numbers are shown.
- **HTTP 403 / 401**: the key is wrong or expired. Get a new one from your data.gov.in "My Account" page.
- **No data for a district**: the dataset may spell it differently (for example Aurangabad / Chhatrapati Sambhajinagar). Check `http://127.0.0.1:5000/api/districts`.
- **Voice**: speaking out loud works in most browsers; voice *input* works best in Google Chrome. A Marathi or Hindi voice must be installed on the device (Android phones usually have them; on Windows add them under Settings → Time & Language → Speech).

## Before sharing this publicly

- Your API key was pasted in a chat, so treat it as exposed: generate a new key on data.gov.in and put the new one in `.env`.
- Never upload `.env` to GitHub (it is already in `.gitignore`).
- The scheme eligibility texts are general guidance; verify them against current official guidelines (scheme names and rules change), and have a native speaker review the Hindi and Marathi wording.
- `app.py` runs in debug mode for local use only. For a real deployment use a production server such as gunicorn.
