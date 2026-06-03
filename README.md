Kaypture (SaaS for client photo delivery and photographer management)



Built for pros, Kaypture runs fast even when many users are active at once. Access stays safe through private galleries clients can view only with permission. Images load quickly thanks to smart resizing that adapts on the fly. Each file gets stamped with a precise timestamp-based ID so nothing loses its place. Communication between systems flows smoothly using a streamlined connection setup.



----------------------------------------------------------------------------------------------------------------------------------------------



Project Setup and Tools Used





KYAPTURE/ <- Root Directory

backend django rest framework api postgresql

Frontend With React Vite And Tailwind Css

Django 5 or newer runs the backend, while DRF handles API logic. PostgreSQL stores data, stepping in as the main database. Authentication leans on SimpleJWT for token control. Images get managed thanks to Pillow doing the heavy lifting. Settings stay separate through python-decouple keeping secrets out of code. Primary keys? uuid6 brings time-sorted UUIDv7 support right into table IDs.

React 18 powers the interface, built fast using Vite. Styling flows through Tailwind CSS, keeping design lean. API calls happen via Axios - tokens renew quietly in the background. Zustand handles shared state without clutter. Each piece fits, working together but staying clear.

PostgreSQL runs locally, also inside Docker containers.

Getting Started with Local Development

1. Backend Setup (Django API)

Open the project folder, then go into backend/. Move past the main level to reach that subdirectory

code

Bash

cd backend

Create and Activate Virtual Environment

code

Bash

python -m venv .venv

Windows:

.venv\Scripts\activate

macOS/Linux:

source .venv/bin/activate

Install Dependencies:

code

Bash

Start by typing pip install followed by -r and then the file named requirements dot txt

Configure Environment Secrets:

Start by copying backend/.env.example. Then make a new file named backend/.env for your local setup. Use that copy as the base

code

Bash

cp .env.example .env

Start by opening the file backend/.env. There, swap out the current details for your PostgreSQL database - use kyapture_DB. Change the SECRET_KEY too, pick something strong. Make it tough to guess, keep it safe.

Apply Migrations:

Start by checking that your local PostgreSQL server is active. The database must match what you named in the .env file. After that, run the command shown below

code

Bash

Run python manage.py migrate using config.settings.development instead of default settings

Create an Administrator Superuser

code

Bash

python manage.py createsuperuser --settings=config.settings.development

Start the Django server

code

Bash

Start the server using python manage dot py with the development settings specified through command line option

Running right now - the backend API lives here: http://127.0.0.1:8000/api/v1/

2. Frontend Setup (React SPA)

Open the folder named frontend/, starting at the main project location

code

Bash

cd ../frontend

Install Node Packages:

code

Bash

npm install

Configure Local Environment:

Create a local environment file named .env.local inside frontend/:

code

Ini

VITE_API_URL=http://localhost:8000/api/v1

VITE_MEDIA_URL=http://localhost:8000/media

Start the Vite development server

code

Bash

npm run dev

Running live on your machine, the photographer's interactive dashboard opens at: http://localhost:5173/. Built right into your local setup, it loads through that address. You’ll find everything responds smoothly once accessed there. This version operates straight from your device. The link points directly to its current home

API Docs and Contracts

Every API path starts with /api/v1/ so front and back connect smoothly. A fixed error format keeps responses clear, no matter the request. One pattern fits all failures, making troubleshooting straightforward. Consistency runs through every endpoint by design.

Start by opening the API_DOCS.md file right there at the project's base folder. That document holds every endpoint explained, along with how requests and responses look in JSON format. Look inside for exact header setups, what security rules apply, plus full payload examples. Everything needed sits together in that one place, no extra hunting required.

Team Git Workflow and Branch Rules

Keeping things tidy and predictable in the repo is up to us - Mausam, Kroman, David - and that means one thing: we follow these rules without exception

Start fresh each time. Working straight on main? Not happening here. Every new thing - code changes or cleanup - goes into its own detached branch first. Isolation comes before integration, always.

Branch Naming Convention:

feature/ for new features (e.g., feature/gallery-crud).

Patch applied under fix/ when resolving issues like expired token errors.

Fix/ when adjusting system settings or changing software parts.

Daily Committing Routine:

Every time you begin, grab the latest updates first. Sync things up by running git pull origin main right away. This step keeps your work aligned with the team's progress. Start here, every single time without skipping.

Start fresh with a new branch: type git checkout -b feature/your-feature-name to switch into it

Commit small, logical changes often with descriptive commit messages.

Start by sending your branch up to GitHub, then follow with creating a Pull Request. Once that’s done, others can review what you’ve added. Moving forward, feedback might come in slowly. After changes land, the project shifts slightly. Progress shows up in small updates like this one.

For every pull request, someone on the team - like Mausam dai - needs to take a look first. Only after that check does it move into main. Approval comes before merging, no exceptions. One clear yes from a teammate keeps things moving forward.