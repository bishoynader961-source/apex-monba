const fs = require('fs');

function walk(dir, filelist = []) {
  if (!fs.existsSync(dir)) return filelist;
  const files = fs.readdirSync(dir);
  files.forEach(file => {
    const filepath = dir + '/' + file;
    if (fs.statSync(filepath).isDirectory()) {
      filelist = walk(filepath, filelist);
    } else if (filepath.endsWith('.tsx')) {
      filelist.push(filepath);
    }
  });
  return filelist;
}

const en = JSON.parse(fs.readFileSync('lib/i18n/locales/en.json', 'utf8'));

const files = walk('app').concat(walk('components'));

// Match t("section.key") or t("section.key.subkey") - proper i18n keys with at least one dot
const keyPattern = /t\("([a-z][a-z0-9]*\.[a-z][a-z0-9.]*)"\)/g;
let allKeys = new Set();

files.forEach(file => {
  const content = fs.readFileSync(file, 'utf8');
  let match;
  while ((match = keyPattern.exec(content)) !== null) {
    allKeys.add(match[1]);
  }
});

let missing = [];
allKeys.forEach(key => {
  if (!en[key]) {
    missing.push(key);
  }
});

console.log('Total unique keys found:', allKeys.size);
console.log('Missing keys:', missing.length);
missing.forEach(k => console.log('  MISSING:', k));