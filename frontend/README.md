# Frontend for CampusRun 
## React + Radix UI + React Router + Vite 

### Set Up 🤩
```
cd frontend 
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
The supplier page calls the Supplier Service through the gateway at `http://localhost:8080/api/suppliers`. To use another address, create `frontend/.env.local` with `VITE_SUPPLIER_API_URL=...`.

Start the gateway and the services first with `docker compose up --build` from the repo root.

Every call sends the access token stored in the browser (`src/utils/session.ts`). Until the User Service login is connected, the supplier page offers **Use a development token** (in `npm run dev` only):
1. Make a token in `supplier-service` with `uv run python scripts/make_token.py --role admin`, or `--role student`.
2. Paste it into that dialog.