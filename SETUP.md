# Setup Guide: Push Existing Repository to GitHub

This guide will help you push an existing local repository to the FFPy GitHub repository.

## Prerequisites

- Git installed on your computer
- A local repository with code you want to push
- GitHub account with access to this repository

## Option 1: Push Existing Repository (Recommended)

If you already have a local Git repository with your code:

### Using HTTPS

```bash
# Navigate to your existing repository
cd /path/to/your/local/repository

# Add this repository as the remote origin
git remote add origin https://github.com/RickArko/FFPy.git

# Verify the remote was added
git remote -v

# Fetch the latest changes from GitHub (including README.md)
git fetch origin

# Merge the remote main branch with your local code
# If you want to keep both histories:
git merge origin/main --allow-unrelated-histories

# Push your code to GitHub
git push -u origin main
```

### Using SSH

```bash
# Navigate to your existing repository
cd /path/to/your/local/repository

# Add this repository as the remote origin
git remote add origin git@github.com:RickArko/FFPy.git

# Verify the remote was added
git remote -v

# Fetch the latest changes from GitHub
git fetch origin

# Merge the remote main branch with your local code
git merge origin/main --allow-unrelated-histories

# Push your code to GitHub
git push -u origin main
```

## Option 2: If You Already Have a Remote Named 'origin'

If your repository already has a remote named 'origin', you'll need to either remove it or rename it:

### Remove existing remote and add new one:
```bash
git remote remove origin
git remote add origin https://github.com/RickArko/FFPy.git
```

### Or rename existing remote and add new one:
```bash
git remote rename origin old-origin
git remote add origin https://github.com/RickArko/FFPy.git
```

## Option 3: Initialize a New Repository

If you don't have a Git repository yet:

```bash
# Navigate to your project folder
cd /path/to/your/project

# Initialize a new Git repository
git init

# Add all files to staging
git add .

# Create your first commit
git commit -m "Initial commit"

# Add the remote repository
git remote add origin https://github.com/RickArko/FFPy.git

# Fetch and merge the README from GitHub
git fetch origin
git merge origin/main --allow-unrelated-histories

# Push your code to GitHub
git push -u origin main
```

## Troubleshooting

### Authentication Issues

**HTTPS:** You may be prompted for your GitHub username and password. As of August 2021, GitHub requires a Personal Access Token (PAT) instead of a password.
- Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token (classic)
- Use the token as your password when prompted

**SSH:** Ensure you have SSH keys set up:
```bash
# Generate SSH key (if you don't have one)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Add SSH key to ssh-agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# Copy public key and add to GitHub (Settings → SSH and GPG keys)
cat ~/.ssh/id_ed25519.pub
```

### Merge Conflicts

If you encounter merge conflicts during `git merge origin/main --allow-unrelated-histories`:

1. Git will tell you which files have conflicts
2. Open the conflicting files and resolve the conflicts manually
3. After resolving, add the files: `git add <filename>`
4. Complete the merge: `git commit -m "Merge remote main branch"`
5. Push to GitHub: `git push -u origin main`

### Force Push (Use with Caution)

If you want to completely replace the remote repository with your local code:

```bash
# WARNING: This will overwrite the remote repository history
git push -u origin main --force
```

⚠️ **Warning:** Force pushing will delete the existing README.md and any other files on GitHub. Only use this if you're sure you want to replace everything.

## Verify Success

After pushing, visit https://github.com/RickArko/FFPy to verify your code is there.

## Next Steps

- Update the README.md with information about your project
- Add a .gitignore file to exclude unwanted files
- Set up branch protection rules if needed
- Configure GitHub Actions for CI/CD if applicable
