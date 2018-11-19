module.exports = {
    root: true,
    env: {
        node: true
    },
    extends: [
        'plugin:vue/essential',
        'eslint:recommended'
    ],
    rules: {
        'no-console': process.env.NODE_ENV === 'production' ? 'error' : 'off',
        'no-debugger': process.env.NODE_ENV === 'production' ? 'error' : 'off',
        'flowtype-errors/show-errors': 2,
        "indent": ["error", 4]
    },
    parserOptions: {
        parser: 'babel-eslint'
    },
    plugins: [
        'flowtype-errors',
        'html'
    ]
};
