# Nexus TMS — Streamlit web edition

This folder contains a browser-based starter for the Traffic Management project. It keeps the original desktop program separate: `start_project.py` uses Tkinter and cannot run as a browser app. The Streamlit edition provides corridor overview, map, traffic history, alerts, and a basic route comparison view.

## Run locally on Windows

Open PowerShell in this folder and run:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

If PowerShell blocks activation, use the environment's executable directly:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

The app creates `traffic_control.db` beside `streamlit_app.py` on first launch and seeds sample Delhi traffic data. To use an existing compatible `traffic_control.db`, place it in this folder before launching. Do not copy `traffic_control.db-journal`; SQLite creates and manages journal files as needed.

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository and upload the contents of this folder.
2. In [Streamlit Community Cloud](https://share.streamlit.io/), choose **Create app**.
3. Select your repository and branch, and set the app file to `streamlit_app.py`.
4. Deploy. Community Cloud installs the packages listed in `requirements.txt`.

## Enable TomTom live traffic

The app requests TomTom Traffic Flow v4 readings for the configured road midpoints when you click **Sync live traffic**. It records successful readings in `traffic_control.db` and shows them in the dashboard and history chart. This uses one API request per road per sync; API access and quota depend on your TomTom account.

In Streamlit Community Cloud, open the app's **Settings → Secrets** and add:

```toml
TOMTOM_API_KEY = "paste-your-TomTom-key-here"
```

Save and reboot the app. For local use, you can set `TOMTOM_API_KEY` as an environment variable in PowerShell before running Streamlit:

```powershell
$env:TOMTOM_API_KEY = "paste-your-TomTom-key-here"
python -m streamlit run streamlit_app.py
```

Never put the real key in `streamlit_app.py`, GitHub, or a committed `secrets.toml` file. Streamlit Secrets keeps the credential out of the source repository. The TomTom account must have Traffic Flow API access enabled.
