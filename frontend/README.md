# Frontend for CampusRun 
## React + Radix UI + React Router + Vite 

### Set Up 🤩
Requires Node 24.18.0 (pinned in `mise.toml`, `.nvmrc` and `package.json` `engines`).

```
cd frontend 
mise install   # or: nvm use
npm install

# Starts local vite server at :5173
npm run dev 

# Useful commands
npm run build
npm run lint
npm run format:check
```

Also, install Prettier and ESLint extensions <br>
Then, at the root level (CampusRun), set VSCode project settings 

```
# Place under CampusRun/.vscode/settings.json 
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

### Connecting to the services
The app calls the services with relative URLs (`/api/users/...`, `/api/suppliers/...`), so behind the gateway they're the same origin as the page.

Under `npm run dev`, the Vite dev server forwards `/api` to `VITE_API_PROXY_TARGET`. It's required: copy `.env.example` to `.env` (it points at the gateway, `http://localhost:8080`), and the dev server refuses to start without it.

Start the gateway and the services first with `docker compose up --build` from the repo root.

### Running in Docker
`docker compose up --build` from the repo root also builds this app (`Dockerfile`) and serves it with nginx (`nginx.conf`) behind the gateway, at http://localhost:8080. That runs the built files, so rebuild to see changes; use `npm run dev` while developing.

Every call sends the access token stored in the browser (`src/utils/session.ts`). Until the User Service login is connected, the supplier page offers **Use a development token** (in `npm run dev` only):
1. Make a token in `supplier-service` with `uv run python scripts/make_token.py --type admin`, or `--type student`.
2. Paste it into that dialog.