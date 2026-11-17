import { createRequire } from "node:module";
import config from "../web/eslint.config.mjs";
const require = createRequire(import.meta.url);
const web = require("../web/package.json");
const siteConfig = [...config, { settings: { react: { version: web.dependencies.react } } }];
export default siteConfig;
