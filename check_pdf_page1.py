import os
from pypdf import PdfReader

def check_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        print(f"Total pages: {len(reader.pages)}")
        print("--- Page 1 Content ---")
        print(reader.pages[0].extract_text())
        print("--- Page 2 Content ---")
        if len(reader.pages) > 1:
            print(reader.pages[1].extract_text())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    target_pdf = "5.达涅利SDM自动炼钢模型四大平衡计算(2)_20260130152512.pdf"
    base_path = "/Users/wenqing/Desktop/VAgent"
    full_path = os.path.join(base_path, target_pdf)
    check_pdf(full_path)
