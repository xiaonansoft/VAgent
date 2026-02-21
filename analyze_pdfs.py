import os
from pydantic import BaseModel
from pypdf import PdfReader

def extract_text_from_pdf(file_path, max_pages=5):
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
    pdf_files = [
        "5.达涅利SDM自动炼钢模型四大平衡计算(2)_20260130152512.pdf",
        "第7章-转炉提钒动力学研究(1).pdf",
        "铁水预处理提钒讲课稿[整理版](1).pdf",
        "黑龙江建龙转炉提钒技术材料--修改--2020.6.13(1).pdf"
    ]
    
    base_path = "/Users/wenqing/Desktop/VAgent"
    
    for pdf in pdf_files:
        full_path = os.path.join(base_path, pdf)
        print(f"--- Analyzing: {pdf} ---")
        if os.path.exists(full_path):
            content = extract_text_from_pdf(full_path)
            # Print first 2000 chars to avoid clutter
            print(content[:2000])
            print("\n" + "="*50 + "\n")
        else:
            print(f"File not found: {full_path}")

if __name__ == "__main__":
    main()
