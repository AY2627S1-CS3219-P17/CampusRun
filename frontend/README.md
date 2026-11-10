<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-11
Scope: AI-added the frontend/.env step, the full-stack prerequisite, the orders and credits routes in the diagram,
       and fixed the VS Code settings path and the directory changes in the setup commands; the rest was written by the team.
Author review: <to be completed by author>
-->

# Frontend
## React + Radix UI + React Router + Vite 

### Set Up 🤩
Requires Node 24.18.0 (pinned in `mise.toml`, `.nvmrc` and `package.json` `engines`) <br>
The dev server sends API calls to the gateway, so first get the full stack running by following
[Running the project](../README.md#running-the-project) in the root README (this sets up the root `.env`).

Then, in `frontend`, copy `.env.example` to `.env` and set:

```
VITE_API_PROXY_TARGET=http://localhost:8080
```

`npm run dev` stops with an error if it's empty.

```
# From the repository root
cd frontend
mise install   # or: nvm use
npm install

# Terminal 1 - from the repository root: containerized BE + FE + Gateway at :8080
docker compose up --build

# Terminal 2 - from frontend/: local FE server at http://localhost:5173
# Work on local FE server for HMR 
npm run dev 

# Useful commands
npm run build
npm run lint
npm run format:check
```

### Mental Model 🤔
```
# Development (npm run dev):

Browser → Vite dev server (:5173)
          ├─ Pages and assets → served by Vite with HMR
          └─ /api/... → VITE_API_PROXY_TARGET (:8080)
                        → gateway nginx
                          ├─ /api/users/...     → user-service
                          ├─ /api/suppliers/... → supplier-service
                          ├─ /api/orders/...    → order-service
                          └─ /api/credits/...   → credit-service


Containerized app (docker compose up):

Browser → gateway nginx (:8080)
          ├─ /api/users/...     → user-service
          ├─ /api/suppliers/... → supplier-service
          ├─ /api/orders/...    → order-service
          ├─ /api/credits/...   → credit-service
          └─ Everything else    → frontend nginx
                                  └─ serves built HTML/CSS/JS
```

### Quality of Life 😊
Also, install Prettier and ESLint extensions <br>
Then, in `.vscode/settings.json` at the repository root, set these VSCode project settings:

```
{
    "eslint.workingDirectories": ["./frontend"],
    "[typescript]": {
        "editor.defaultFormatter": "esbenp.prettier-vscode",
        "editor.formatOnSave": true,
        "editor.formatOnSaveMode": "file"
    },
    "[typescriptreact]": {
        "editor.defaultFormatter": "esbenp.prettier-vscode",
        "editor.formatOnSave": true,
        "editor.formatOnSaveMode": "file"
    }
}
```

### Folder Structure 🤣
Everything lies under `frontend/src`
1. `api` -> API calls to various BE services 
2. `assets` -> UI images
3. `components` -> Reusable React components  
4. `pages` -> React Router pages 
5. `types` -> Reusable types 
6. `utils` -> Reusable helper functions