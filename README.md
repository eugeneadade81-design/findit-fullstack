# FindIt Full Stack

Complete self-contained campus lost-and-found app built for the `FindIt_Proposal_v2.docx` concept.

## Stack

- Frontend: HTML, CSS, JavaScript
- Backend: Python `http.server` + custom API
- Database: SQLite
- Installability: PWA manifest + service worker

## Features

- Student registration and login
- Session-based authentication
- Lost/found item reporting
- Listing search and filters
- Smart match suggestions using TF-IDF cosine similarity plus category/location boosts
- Ownership claims
- Admin analytics and status moderation
- Local SQLite persistence

## Demo accounts

- Admin: `admin@knust.edu.gh` / `admin123`
- Student: `ama@knust.edu.gh` / `student123`

## Run locally

```powershell
cd "C:\Users\HP\Documents\New project\findit-fullstack"
python server.py
```

Then open:

`http://127.0.0.1:8000`

If port `8000` is busy, start on another port:

```powershell
python server.py 8010
```

## Android

Because this is a PWA, it can be installed from a mobile browser using the browser's "Add to Home Screen" or install prompt when hosted online.

## Deploy online

The project is now deployment-ready with:

- `Dockerfile`
- `render.yaml`
- environment-based host/port support
- PostgreSQL support via `DATABASE_URL`
- Cloudinary image upload support via env vars

### Quick option: Render

1. Push this folder to GitHub
2. Create a new Render Web Service from the repo
3. Render will detect `render.yaml` / `Dockerfile`
4. After deploy, open the live URL

Important:

- The app currently uses SQLite stored in `data/findit.db`
- On many free hosts, local disk may be ephemeral
- That means app data can reset after redeploy/restart unless you use persistent storage

Production env vars:

- `DATABASE_URL`
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

For a school demo, this is usually fine.
For real public use, the next production step should be moving from SQLite to a hosted database.

## GitHub upload

Upload the entire `findit-fullstack` folder as a repository.
