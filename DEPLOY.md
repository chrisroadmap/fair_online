# Deploying the FaIR dashboard to PythonAnywhere (fairmodel.net)

This folder is a complete, self-contained Flask application. Everything it
needs — the FaIR model, the calibrated climate parameters, and the emissions
data — is bundled inside `data/` and `static/`, so it does not need internet
access at runtime.

## 1. Get the code onto PythonAnywhere

Since your domain already points at a placeholder web app, you'll be
replacing that app's code rather than creating a new one.

1. Log in to [pythonanywhere.com](https://www.pythonanywhere.com) and open a
   **Bash console** (Dashboard → New console → Bash).
2. Upload `fairdash.zip` (this bundle) using the **Files** tab — click
   "Upload a file" and put it somewhere like `/home/yourusername/`.
3. Back in the Bash console, unzip it into place. If your existing web app's
   source is at `/home/yourusername/mysite`, either replace it or pick a new
   folder — either works, you'll point the WSGI file at whichever you use:

   ```bash
   cd /home/yourusername
   unzip fairdash.zip -d fairdash
   ```

## 2. Create a virtualenv and install dependencies

`fair` (the climate model package) supports Python 3.8–3.12, so pick a
3.10/3.11/3.12 interpreter when creating the virtualenv (check what's
available with `python3.11 --version`, etc.):

```bash
mkvirtualenv --python=/usr/bin/python3.11 fairdash-env
pip install -r /home/yourusername/fairdash/requirements.txt
```

This installs Flask, the `fair` model, numpy, scipy and pandas. It should
take a minute or two.

## 3. Point your web app at this code

1. Go to the **Web** tab in the PythonAnywhere dashboard and open the web app
   that's already configured for **fairmodel.net**.
2. Under **Virtualenv**, enter the path to the environment you just made,
   e.g. `/home/yourusername/.virtualenvs/fairdash-env` (PythonAnywhere shows
   the exact path after `mkvirtualenv` finishes — copy it from the console
   output, or run `workon fairdash-env && echo $VIRTUAL_ENV`).
3. Under **Code**, set:
   - **Source code**: `/home/yourusername/fairdash`
   - **Working directory**: `/home/yourusername/fairdash`
4. Click the **WSGI configuration file** link (still on the Web tab) and
   replace its entire contents with:

   ```python
   import sys

   path = '/home/yourusername/fairdash'
   if path not in sys.path:
       sys.path.insert(0, path)

   from app import app as application
   ```

   (Replace `yourusername` with your actual PythonAnywhere username, and
   adjust the path if you unzipped somewhere else.)
5. Under **Static files**, add an entry mapping URL `/static/` to directory
   `/home/yourusername/fairdash/static` — this lets PythonAnywhere serve
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
- **"iirf_0 nan" or similar model errors** — make sure the whole `data/`
  folder was uploaded and unzipped (it should contain
  `species_configs_properties.csv`, `central_config.csv`,
  `emissions.csv`, `natural_forcing.csv`, `climate_meta.json`).
- **Blank page / static files 404** — double-check the static files mapping
  in step 3.5, or just make sure `templates/` and `static/` sit directly
  inside the source code folder you set in step 3.3.

## 5. Updating later

To ship a code change: upload the new files (or `git pull` if you put this
under version control — recommended), then just click **Reload** on the Web
tab again. No need to touch the WSGI file or virtualenv again unless you add
a new Python dependency (in which case `pip install` it into the same
virtualenv first).

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
