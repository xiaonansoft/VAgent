import os
from pypdf import PdfReader

def extract_text_from_pdf(file_path, max_pages=20):
    try:
        reader = PdfReader(file_path)
        text = ""
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            text += page.extract_text() + "\n\n"
        return text
    except Exception as e:
        return f"Error reading {file_path}: {str(e)}"

def main():
    target_pdf = "第7章-转炉提钒动力学研究(1).pdf"
    base_path = "/Users/wenqing/Desktop/VAgent"
    full_path = os.path.join(base_path, target_pdf)
    
    print(f"--- Analyzing: {target_pdf} ---")
    if os.path.exists(full_path):
        # Read pages 1-10 to find Delta G constants
        content = extract_text_from_pdf(full_path, max_pages=10)
        # Filter for lines with "G =" or "J/mol" or "T"
        lines = content.split('\n')
        for line in lines:
            if "G" in line or "J/mol" in line or "T" in line:
                 print(line)
    else:
        print(f"File not found: {full_path}")

if __name__ == "__main__":
    main()
