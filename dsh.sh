git add dsh.sh
git commit -m "Make dsh.sh executable"
git checkout 6762140e4c683be2a960c72915e5ad5c96d893e8 -- dashboard.html
chmod +x dsh.sh
git commit -m "Revert dashboard.html to previous version before updates"
git push origin main
