import os
from pypdf import PdfReader

def extract_text_with_keywords(file_path, keywords, max_pages=30):
    try:
        reader = PdfReader(file_path)
        print(f"--- Analyzing: {os.path.basename(file_path)} ---")
        
        found_content = ""
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            text = page.extract_text()
            # Check if any keyword is in the page
            if any(k in text for k in keywords):
                print(f"--- Page {i+1} ---")
                print(text[:1000]) # Print first 1000 chars of relevant page
                found_content += text + "\n"
        return found_content
    except Exception as e:
        print(f"Error: {e}")
        return ""

def main():
    base_path = "/Users/wenqing/Desktop/VAgent"
    files = [
        "黑龙江建龙转炉提钒技术材料--修改--2020.6.13(1).pdf",
        "铁水预处理提钒讲课稿[整理版](1).pdf"
    ]
    
    keywords = ["装入", "冷却剂", "枪位", "供氧", "底吹", "硅", "温度", "加料", "氧化铁皮"]
    
    for f in files:
        full_path = os.path.join(base_path, f)
        if os.path.exists(full_path):
            extract_text_with_keywords(full_path, keywords)
        else:
            print(f"File not found: {full_path}")

if __name__ == "__main__":
    main()
