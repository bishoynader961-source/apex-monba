import re
file_path = r'E:\my progam pharmacy\app\dashboard\label-engine\page.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

new_print = '''  const handlePrint = async () => {
    const canvas = document.querySelector("canvas");
    if (!canvas) {
      toast({ title: "Error", message: "No canvas found", variant: "destructive" });
      return;
    }
    const dataUrl = canvas.toDataURL("image/png");
    const iframe = document.createElement("iframe");
    iframe.style.display = "none";
    document.body.appendChild(iframe);
    const doc = iframe.contentWindow?.document;
    if (doc) {
      doc.open();
      doc.write(<html><head><title>Print Label</title></head><body style="margin:0;display:flex;justify-content:center;align-items:center;"><img src="" onload="window.print();" /></body></html>);
      doc.close();
      setTimeout(() => { if (document.body.contains(iframe)) document.body.removeChild(iframe); }, 10000);
      toast({ title: "Success", message: "Print dialog opened" });
    } else {
      toast({ title: "Error", message: "Failed to create print frame", variant: "destructive" });
    }
  };'''

text = re.sub(
    r'  const handlePrint = async \(\) => \{[\s\S]*?toast\(\{ title: "Success", message: "Print dialog opened \(fallback\)" \}\);\n    \}\n  \};',
    new_print,
    text
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
