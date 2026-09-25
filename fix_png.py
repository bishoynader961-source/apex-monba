import re
file_path = r'E:\my progam pharmacy\app\dashboard\label-engine\page.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

new_export_png = '''  const handleExportPNG = async () => {
    const canvas = document.querySelector("canvas");
    if (!canvas) return;
    try {
      const { save } = await import("@tauri-apps/plugin-dialog");
      const { writeFile } = await import("@tauri-apps/plugin-fs");
      const filePath = await save({
        filters: [{ name: "Image", extensions: ["png"] }],
        defaultPath: label-.png,
      });
      if (!filePath) return;

      const dataUrl = canvas.toDataURL("image/png");
      const base64Data = dataUrl.replace(/^data:image\/png;base64,/, "");
      
      const binaryString = window.atob(base64Data);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      
      await writeFile(filePath, bytes);
      toast({ title: "Success", message: "PNG exported" });
    } catch (err) {
      const link = document.createElement("a");
      link.download = label-.png;
      link.href = canvas.toDataURL("image/png");
      link.click();
      toast({ title: "Success", message: "PNG exported (browser)" });
    }
  };'''

text = re.sub(
    r'  const handleExportPNG = \(\) => \{[\s\S]*?toast\(\{ title: "Success", message: "PNG exported" \}\);\n  \};',
    new_export_png,
    text
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
