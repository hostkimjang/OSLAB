module.exports = {
  testDir: "./apps/web/tests",
  testMatch: /.*\.spec\.js/,
  timeout: 180000,
  use: {
    browserName: "chromium",
  },
};
