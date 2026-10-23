#!/bin/bash

# Repository and branch to install: the HF superproject with its submodules.
# REPO_BRANCH can be overridden (after the merge to main: main).
REPO_URL="https://github.com/stiftung-humboldtforum/mediensteuerung"
REPO_BRANCH="${REPO_BRANCH:-update/2026-10}"

# Inside a checkout of the superproject (its files, not its remote URL), install
# there; otherwise clone it first.
if [ -f docker-compose.yml ] && [ -d install ] && [ -d backend ]; then
  inside_repo=true
else
  inside_repo=false
fi

if [ "$inside_repo" = false ]; then
  git clone -j8 --recurse-submodules -b "$REPO_BRANCH" "$REPO_URL"
  cd mediensteuerung || exit
fi

scripts=("./install/env_setup.sh" "./install/ssl_setup.sh" "./install/docker_build.sh" "./install/setup_user.sh" "./install/frontend_setup.sh")

for script in "${scripts[@]}"; do
  # Check if the script has been executed successfully in a previous run
  flag_file="${script}.done"

  if [ ! -e "$flag_file" ]; then
    read -p "Do you want to run $script interactively? (y/n): " -n 1 -r
    echo # Move to a new line

    if [[ $REPLY =~ ^[Yy]$ ]]; then
      # Run the script interactively
      if ./"$script"; then
        # Only create the flag file if the script executed successfully
        touch "$flag_file"
      else
        echo "$script failed. Exiting the installation."
        exit 1
      fi
    else
      echo "Skipping $script..."
    fi
  else
    echo "$script has already been run successfully."
  fi
done

echo "Done!"

