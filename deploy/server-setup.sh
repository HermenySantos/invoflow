#!/bin/sh
# One-time setup of a fresh Ubuntu 24.04 server for Invoflow. Run as root:
#   ssh root@SERVER 'sh -s' < deploy/server-setup.sh "ssh-ed25519 AAAA... deploy@github"
# The argument is the PUBLIC key GitHub Actions will use to deploy.
set -eu
DEPLOY_KEY="${1:?pass the deploy public key as the first argument}"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y upgrade
apt-get -y install ca-certificates curl ufw unattended-upgrades fail2ban

# Security updates install themselves.
dpkg-reconfigure -f noninteractive unattended-upgrades

# Firewall: SSH and web only. Postgres is never published.
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

# Docker Engine + compose plugin from Docker's apt repository.
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Deploy user: key login only, may run docker, owns /opt/invoflow.
id deploy >/dev/null 2>&1 || adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
echo "$DEPLOY_KEY" > /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
install -d -o deploy -g deploy /opt/invoflow

# No password logins over SSH (keys only); root keeps key access for recovery.
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart ssh

echo "Done. Next: put the production .env in /opt/invoflow/.env (chmod 600, owner deploy)."
