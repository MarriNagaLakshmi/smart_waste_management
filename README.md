# Neighbourhood Waste Desk — Smart Waste Management

A Flask-based local demo with resident accounts, complaint submission, unique references, photo upload, optional geolocation, private resident dashboard, complaint tracking, staff assignment, status history, resident feedback and area/status reports.

## Local setup (Windows PowerShell)
1. Extract this folder and open it in VS Code.
2. Open Terminal in this folder.
3. Create a virtual environment:
   ```powershell
   py -3.12 -m venv .venv
   ```
4. Install packages:
   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
5. Start the site:
   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```
6. Open http://127.0.0.1:5000

If `py` is unavailable, use your installed Python executable with `-m venv .venv` and then the same `.venv\Scripts\python.exe` commands.

## Demo administrator
- Email: `admin@waste.local`
- Password: `Admin123!`

Sign up as a resident to submit complaints. Residents only see their own complaints and updates. The admin can review all complaints, assign a worker, set Pending / Assigned / In Progress / Completed / Recycled, and publish a message visible to the resident. Complaint references are generated using date plus a random UUID segment. A status timeline is stored for every update.

## Features
- Resident registration and login (hashed passwords)
- Unique complaint number generated automatically
- Category, description, location, date/time, image and optional browser coordinates
- Complaint photo upload (PNG/JPG/JPEG/WebP, 5 MB max)
- Resident-only complaint dashboard and status filtering
- Track page with chronological status messages
- Admin complaint management and worker assignment
- Pending, completed and recycled states
- Area-wise and status reports
- Resolution feedback
- Responsive, restrained editorial style (warm neutral, olive and terracotta palette)

## Data and deployment notes
This package runs locally with SQLite so it works immediately without cloud credentials. The original project plan mentions Supabase PostgreSQL, Supabase Auth and Storage; those services are **not wired into this local demo**. `/.env.example` lists placeholders only. Before public deployment, configure a strong `SECRET_KEY`, replace the demo admin password, use Supabase or a managed database, add Supabase Auth/Storage integration, set secure cookie/HTTPS settings, and configure Render environment variables. Do not deploy the demo administrator credentials publicly.

For Render, use a production WSGI server such as Gunicorn (add `gunicorn` to requirements and use `gunicorn app:app` as the start command). SQLite on an ephemeral Render filesystem is not durable; use Supabase PostgreSQL for production persistence. Maps currently store optional latitude/longitude but do not include a map view; Leaflet/OpenStreetMap can be added with configured tile attribution.
