#!/bin/bash

#
# Expose a 'run' command that runs code either directly on this VM, or if IMAGE
# is set, in a Docker container on the VM instead. The mode where IMAGE is
# unset is intended for later use with OS X.
#
# When running in container mode, wire up various cache directories within the
# container back to a directory that Travis knows to keep a copy of. This
# causes built wheels, apt package lists, and PyPI source archives to all
# be cached.
#
# In either case, "/tmp/zato" contains the checked out Git repository.
#
# Usage:
#   source $TRAVIS_BUILD_DIR/.travis/setup.sh
#   run py.test -m /tmp/zato/...
#

echo travis_fold:start:begin_zato_setup_sh
set -e $BASH_TRACE
set -o pipefail


#
# Usage: on_exit "<cmdline>"
# Arrange for "<cmdline>" to be eval'd during shell exit.
#

function on_exit()
{
    on_exit_funcs+=("$1")
}

function do_on_exit()
{
    for i in "${on_exit_funcs[@]}"
    do
        eval "$i"
    done
}

on_exit_funcs=()
trap do_on_exit EXIT


#
# Usage: cache_setup <user> <path>
#
# Arrange for /tmp/travis-cache[/foo/bar] to be created and owned by <user>, and
# mount the VM's own /foo/bar directory into the cache.
#
function cache_setup()
{
    local user="$1"; shift
    local path="$1"; shift

    sudo mkdir -p "/tmp/travis-cache$path"
    sudo mkdir -p "$path"
    sudo mount --bind "/tmp/travis-cache$path" "$path"
    on_exit "sudo umount -l '$path'"
    sudo chown -R "$user:" "$path"
}

cache_setup root /opt/zato/python
cache_setup root /root/.cache/pip
cache_setup root /var/cache/apk
cache_setup root /var/cache/apt
cache_setup root /var/lib/apt
cache_setup $(whoami) "$HOME/.cache/pip"

# chown everything to Travis UID on exit so caching succeeds.
on_exit "sudo chown -R $(whoami): /tmp/travis-cache"


function run()
{
    if [ "$IMAGE" ]
    then
        docker exec --user $(whoami) target "$@"
    else
        "$@"
    fi
}

if [ "$IMAGE" ]; then
    # Arrange for the container to be downloaded and started, with a filesystem
    # that borrows a lot from the host VM.
    docker run \
        --name target \
        --volume $HOME:$HOME \
        --volume /tmp/travis-cache/opt/zato/python:/opt/zato/python \
        --volume /tmp/travis-cache/root/.cache/pip:/root/.cache/pip \
        --volume /tmp/travis-cache/var/cache/apk:/var/cache/apk \
        --volume /tmp/travis-cache/var/cache/apt:/var/cache/apt \
        --volume /tmp/travis-cache/var/lib/apt:/var/lib/apt \
        --detach \
        "$IMAGE" \
        sleep 86400

    # Create a container account matching the VM user. Avoid useradd because
    # it's missing in Alpine.
    echo "$(whoami)::$(id -u):$(id -g)::$HOME:/bin/sh" |\
        docker exec bash -c 'cat >> /etc/passwd'

    # Some official images lack sudo, which breaks install.sh.
    if [ "${IMAGE:0:6}" = "centos" ]
    then
        docker exec target yum -y install sudo
    elif [ "${IMAGE:0:6}" = "alpine" ]
    then
        docker exec target apk update
        docker exec target apk add sudo bash
    elif [ "${IMAGE:0:6}" = "ubuntu" -o "${IMAGE:0:6}" = "debian" ]
    then
        docker exec target apt-get update
        docker exec target apt-get -y install sudo
    fi
fi

echo travis_fold:start:end_zato_setup_sh
