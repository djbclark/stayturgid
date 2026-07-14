# CFEngine Build project commands. Policy logic remains in device/termux/cfengine.

cfbs-validate:
    cd device/termux/cfengine && cfbs validate
    cf-promises -f "{{ repo }}/device/termux/cfengine/policy/stayturgid.cf"
    cf-promises -f "{{ repo }}/device/termux/cfengine/policy/cf-serverd.cf"

cfbs-build: cfbs-validate
    cd device/termux/cfengine && cfbs build
    diff -r --exclude=cfbs.json device/termux/cfengine/policy device/termux/cfengine/out/masterfiles
