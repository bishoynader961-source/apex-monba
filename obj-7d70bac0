const fs = require('fs');
const path = require('path');

function findI18nKeys(dir, keys = new Set()) {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      findI18nKeys(fullPath, keys);
    } else if (file.endsWith('.tsx') || file.endsWith('.ts')) {
      const content = fs.readFileSync(fullPath, 'utf8');
      // Match t("key") and t('key') patterns
      const matches = content.match(/t\(["']([^"')]+)["']/g);
      if (matches) {
        matches.forEach(m => {
          const key = m.match(/t\(["']([^"')]+)["']/)[1];
          keys.add(key);
        });
      }
    }
  }
  return keys;
}

function loadLocaleKeys(localeFile) {
  const content = fs.readFileSync(localeFile, 'utf8');
  const json = JSON.parse(content);
  return new Set(Object.keys(json));
}

const appDir = 'E:/my progam pharmacy/app';
const localeFile = 'E:/my progam pharmacy/lib/i18n/locales/en.json';

const usedKeys = findI18nKeys(appDir);
const definedKeys = loadLocaleKeys(localeFile);

console.log('Total used keys:', usedKeys.size);
console.log('Total defined keys:', definedKeys.size);

const missingKeys = [...usedKeys].filter(k => !definedKeys.has(k));
console.log('\nMissing keys (' + missingKeys.length + '):');
missingKeys.sort().forEach(k => console.log('  ' + k));

const unusedKeys = [...definedKeys].filter(k => !usedKeys.has(k));
console.log('\nUnused keys (' + unusedKeys.length + '):');
unusedKeys.sort().forEach(k => console.log('  ' + k));