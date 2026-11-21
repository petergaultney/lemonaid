# The body of the suite's `tmux`. tests/tmux_guard.py writes the script: these lines,
# after the values of real, uid, guarded (socket paths joined by ":") and refusals.

unset CDPATH
socket=
label=
while getopts :2c:CDdf:lL:NqS:T:uUvV option; do
    case $option in
    L) label=$OPTARG ;;
    S) socket=$OPTARG ;;
    esac
done

# tmux's own order: -S, then the server in TMUX unless -L names one, then the -L name
# or "default" in TMUX_TMPDIR, or in /tmp when TMUX_TMPDIR doesn't resolve.
if [ -z "$socket" ]; then
    if [ -z "$label" ] && [ -n "${TMUX:-}" ] && [ "${TMUX#,}" = "$TMUX" ]; then
        socket=${TMUX%%,*}
    else
        base=
        [ -n "${TMUX_TMPDIR:-}" ] && base=$(cd "$TMUX_TMPDIR" 2>/dev/null && pwd -P)
        socket=${base:-$(cd /tmp && pwd -P)}/tmux-$uid/${label:-default}
    fi
fi
case $socket in
*/*) directory=${socket%/*} ;;
*) directory=. ;;
esac
if canonical=$(cd "${directory:-/}" 2>/dev/null && pwd -P); then
    socket=${canonical%/}/${socket##*/}
fi

# -ef compares the files themselves, so a link to a guarded socket matches it too.
reached=
set -f
IFS=:
for server in $guarded; do
    if [ "$socket" = "$server" ] || [ "$socket" -ef "$server" ]; then
        reached=$server
    fi
done
IFS=' '
if [ -n "$reached" ]; then
    echo "tmux guard: refused \`tmux $*\`: it would reach $reached, the developer's own server" >&2
    echo "tmux $* -> $reached" >>"$refusals"
    exit 1
fi
exec "$real" "$@"
