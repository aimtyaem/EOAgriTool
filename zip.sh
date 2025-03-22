zip -r deploy.zip . -x "venv/*" ".git/*" ".github/*" "github"
az webapp deployment source config-zip --resource-group EOAgriTool --name EOAgriTool --src deploy.zip
git remote add azure https://eoagritool-cwfzfndaazauawex.canadacentral-01.azurewebsites.net/EOAgriTool
git push azure main
