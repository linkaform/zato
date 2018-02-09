#!/bin/bash

#
# Try running "alembic upgrade head" against ancient MySQL and PostgreSQL
# database snapshots.
#

set -e $BASH_TRACE
source $TRAVIS_BUILD_DIR/.travis/setup.sh


# Install Zato.
echo travis_fold:start:install_zato
[ "$VIRTUAL_ENV" ] && deactivate
cd $TRAVIS_BUILD_DIR/code
./install.sh
echo travis_fold:end:install_zato


echo travis_fold:start:install_db_clients
# Install Redis and client utilities.
sudo apt-get install -y \
    mysql-client-5.6 \
    redis-server \
    postgresql-client
echo travis_fold:end:install_db_clients


#
# Try MySQL.
#

echo travis_fold:start:start_mysql
docker run \
    --name mysql \
    --detach \
    --publish 13306:3306 \
    --env MYSQL_ROOT_PASSWORD=x \
    mysql:5.5

cat > $HOME/.my.cnf <<-EOF
[client]
host = 127.0.0.1
port = 13306
password = x
user = root
EOF

on_exit 'docker rm --force mysql'

while ! mysql </dev/null
do
    sleep 3
done
echo travis_fold:end:start_mysql


echo travis_fold:start:create_cluster
mysqladmin create db
mysqladmin create db-head

rm -rf $HOME/cluster.mysql
mkdir $HOME/cluster.mysql

./bin/zato quickstart create \
    $HOME/cluster.mysql \
    mysql \
    localhost 6379 \
    --kvdb_password="" \
    --odb_db_name="db" \
    --odb_host="127.0.0.1" \
    --odb_password="x" \
    --odb_port="13306" \
    --odb_user="root" \
    --servers="1"
echo travis_fold:end:create_cluster

# Save quickstart's output, recreate the DB, restore the ancient snapshot, apply
# the Alembic stamp, then run Alembic.
mysqldump db | mysql db-head
mysqladmin --force drop db
mysqladmin create db

gzip -cd ../.travis/db-snapshots/mysql_2.0.8.sql.gz | mysql db
mysql db -e "UPDATE alembic_version SET version_num = '0029_ae7849785be8'"

echo travis_fold:start:run_alembic
./bin/_zato-alembic $HOME/cluster.mysql/server1 upgrade head
echo travis_fold:end:run_alembic
