git clone https://github.com/aimtyaem/EOAgriTool.git
cd EOAgriTool

git fetch origin

for branch in main github; do
  git checkout "$branch"
  git pull origin "$branch"
  git merge origin/gh-pages --allow-unrelated-histories
  git push origin "$branch"
done