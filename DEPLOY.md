# Deploying fair_online to PythonAnywhere (fairmodel.net)

This folder is a complete, self-contained Flask application, also published
at [github.com/chrisroadmap/fair_online](https://github.com/chrisroadmap/fair_online).
Everything it needs — the FaIR model, the calibrated climate parameters, and
the emissions data — is bundled inside `data/` and `static/`, so it does not
need internet access at runtime.

Paths below assume PythonAnywhere username `chrisroadmap` and that the repo
is cloned to `/home/chrisroadmap/fair_online` — adjust if you put it
somewhere else.

## 1. Get the code onto PythonAnywhere

Since your domain already points at a placeholder web app, you'll be
replacing that app's code rather than creating a new one. Because this is
now a real git repo, cloning it directly is cleaner than uploading a zip —
it also makes step 5 (updating later) a one-line `git pull`.

1. Log in to [pythonanywhere.com](https://www.pythonanywhere.com) and open a
   **Bash console** (Dashboard → New console → Bash).
2. Clone the repo:

   ```bash
   cd ~
   git clone https://github.com/chrisroadmap/fair_online.git
   ```

> **Note on old files in this repo:** if `fair_online/` also still has an
> older `flask_app.py` / `config.cfg` / RCP-and-matplotlib prototype in it
> from before, that's harmless — the WSGI file below imports specifically
> from `app.py` (the current Flask app in this bundle), so the old files
> just sit there unused. Worth deleting them at some point to avoid future
> confusion, but not required for this to work.

## 2. Create a virtualenv and install dependencies

`fair` (the climate model package) supports Python 3.8–3.12, so pick a
3.10/3.11/3.12 interpreter when creating the virtualenv (check what's
available with `python3.11 --version`, etc.).

**Use the built-in `venv` module rather than `mkvirtualenv`** —
`virtualenvwrapper`'s `mkvirtualenv` has been producing broken environments
on PythonAnywhere recently (pip failing with an `ImportError` on
`_posixsubprocess` before it even gets to installing anything, which isn't
related to this app — it means the environment itself didn't set up right):

```bash
python3.11 -m venv ~/.virtualenvs/fair_online-env
source ~/.virtualenvs/fair_online-env/bin/activate
pip install --upgrade pip
pip install -r /home/chrisroadmap/fair_online/requirements.txt
```

This installs Flask, the `fair` model, numpy, scipy and pandas. It should
take a minute or two. If you still hit the same `_posixsubprocess` error
here, run `python3.11 -c "import subprocess"` on its own first — if *that*
fails too, the base `python3.11` on your account is the problem, and it's
worth trying `python3.10` or `python3.12` instead, or reaching out to
PythonAnywhere support.

## 3. Point your web app at this code

1. Go to the **Web** tab in the PythonAnywhere dashboard and open the web app
   that's already configured for **fairmodel.net**.
2. Under **Virtualenv**, enter:
   `/home/chrisroadmap/.virtualenvs/fair_online-env`
3. Under **Code**, set:
   - **Source code**: `/home/chrisroadmap/fair_online`
   - **Working directory**: `/home/chrisroadmap/fair_online`
4. Click the **WSGI configuration file** link (still on the Web tab) and
   replace its entire contents with:

   ```python
   import sys

   path = '/home/chrisroadmap/fair_online'
   if path not in sys.path:
       sys.path.insert(0, path)

   from app import app as application
   ```

5. Under **Static files**, add an entry mapping URL `/static/` to directory
   `/home/chrisroadmap/fair_online/static` — this lets PythonAnywhere serve
   `plotly.min.js`, `style.css` and `app.js` directly (faster than going
   through Flask), though the app works fine without this too.
6. Click the big green **Reload** button at the top of the Web tab.

## 4. Check it

Visit **https://fairmodel.net** — you should see the dashboard load, and
clicking "Run scenario" should populate the charts within a second or two.

If something goes wrong, the **Error log** and **Server log** links on the
Web tab are the first place to look. Common issues:

- **Import error for `fair`, `flask`, `numpy` etc.** — the virtualenv path
  on the Web tab doesn't match where you ran `pip install`. Re-check step 3.
- **`_posixsubprocess` / pip crashes while installing** — see the note at
  the end of step 2; recreate the venv with `python3.11 -m venv` rather than
  `mkvirtualenv`.
- **"iirf_0 nan" or similar model errors** — make sure the whole `data/`
  folder made it into the clone (it should contain
  `species_configs_properties.csv`, `central_config.csv`,
  `emissions.csv`, `natural_forcing.csv`, `climate_meta.json`).
- **Blank page / static files 404** — double-check the static files mapping
  in step 3.5, or just make sure `templates/` and `static/` sit directly
  inside `/home/chrisroadmap/fair_online`.
- **WSGI file imports the wrong app** — if there's an old `flask_app.py`
  prototype still in the repo, make sure the WSGI file says
  `from app import app as application`, not `from flask_app import ...`.

## 5. Updating later

To ship a code change: `git pull` inside `/home/chrisroadmap/fair_online`,
then click **Reload** on the Web tab. No need to touch the WSGI file or
virtualenv again unless you add a new Python dependency (in which case
`pip install` it into `fair_online-env` first).

## About the data bundled in this app

- `data/species_configs_properties.csv`, `data/central_config.csv` — species
  and climate parameters from the **fair-calibrate v1.4.1** ensemble
  (Smith et al., 2024, https://doi.org/10.5194/egusphere-2024-708). The
  "central" configuration is the real ensemble member whose emergent
  equilibrium climate sensitivity is closest to the ensemble median
  (ECS ≈ 2.96°C, TCR ≈ 1.68°C).
- `data/emissions.csv`, `data/natural_forcing.csv` — the AR6 Working Group
  III scenario categories used in that same calibration (fetched from
  `github.com/OMS-NetZero/FAIR`, examples/data), trimmed to 1750–2100 and to
  the species this app tracks.

No external network access is required at runtime — everything the model
needs is in these bundled files.
