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
3. `components` -> Reusable React components across multiple pages 
4. `pages` -> React Router pages 
5. `types` -> Reusable types 
6. `utils` -> Reusable helper functions 