import json
import sys

def main():
    output_path = r"C:\Users\Acer\Documents\lab-lucas\rca-agent-lab\.rca-work\bugs-app-delivery-kpi-351d5db0b672\agent-review.json"

    with open(output_path, 'r', encoding='utf-8') as f:
        review = json.load(f)

    # Accept all clarification questions
    for q in review.get('clarification_questions', []):
        q['status'] = 'accepted'
        q['answer'] = 'Sugestões de triagem aceitas pelo usuário.'

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(review, f, indent=2, ensure_ascii=False)
        
    print(f"agent-review.json clarification questions accepted.")

if __name__ == "__main__":
    main()
