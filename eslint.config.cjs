/** Host-only lint configuration; nothing here is deployed to Android. */
module.exports = [
    {
        files: ["device/autojs6/**/*.js"],
        languageOptions: {
            ecmaVersion: 5,
            sourceType: "script",
            globals: {
                app: "readonly",
                auto: "readonly",
                android: "readonly",
                context: "readonly",
                console: "readonly",
                device: "readonly",
                files: "readonly",
                importClass: "readonly",
                module: "readonly",
                runtime: "readonly",
                setInterval: "readonly",
                sleep: "readonly",
                timers: "readonly",
                toast: "readonly",
            },
        },
        rules: {
            "constructor-super": "error",
            "eqeqeq": ["error", "always"],
            "no-constant-condition": "error",
            "no-duplicate-case": "error",
            "no-dupe-keys": "error",
            "no-self-assign": "error",
            "no-shadow": "warn",
            "no-unreachable": "error",
            "no-unused-vars": ["warn", { "args": "none", "caughtErrors": "none" }],
            "no-var": "off",
            "valid-typeof": "error",
        },
    },
];
