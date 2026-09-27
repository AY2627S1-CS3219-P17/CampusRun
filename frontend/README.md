# Frontend
## React + Radix UI + React Router + Vite 

### Set Up 🤩
Requires Node 24.18.0 (pinned in `mise.toml`, `.nvmrc` and `package.json` `engines`) <br>
Remember to copy any repo-wide `.env.example` files to `.env` and fill it in 

```
cd frontend 
mise install   # or: nvm use
npm install

# Terminal 1 - Start containerized BE + FE + Gateway at :8080
cd CampusRun
docker compose up --build

# Terminal 2 - Start local FE server at :5173
# Work on local FE server for HMR 
cd frontend 
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
                          └─ /api/suppliers/... → supplier-service


Containerized app (docker compose up):

Browser → gateway nginx (:8080)
          ├─ /api/users/...     → user-service
          ├─ /api/suppliers/... → supplier-service
          └─ Everything else    → frontend nginx
                                  └─ serves built HTML/CSS/JS
```

### Quality of Life 😊
Also, install Prettier and ESLint extensions <br>
Then, at the root level: `CampusRun/.vscode.settings.json`, set VSCode project settings 

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