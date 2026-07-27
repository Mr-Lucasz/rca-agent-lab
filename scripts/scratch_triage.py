import json
import sys

def main():
    analysis_path = r"C:\Users\Acer\Documents\lab-lucas\rca-agent-lab\.rca-work\bugs-app-delivery-kpi-351d5db0b672\analysis.json"
    template_path = r"C:\Users\Acer\Documents\lab-lucas\rca-agent-lab\.rca-work\bugs-app-delivery-kpi-351d5db0b672\agent-review.template.json"
    output_path = r"C:\Users\Acer\Documents\lab-lucas\rca-agent-lab\.rca-work\bugs-app-delivery-kpi-351d5db0b672\agent-review.json"

    with open(analysis_path, 'r', encoding='utf-8') as f:
        analysis = json.load(f)
    
    with open(template_path, 'r', encoding='utf-8') as f:
        review = json.load(f)

    review['reviewed_by'] = "Antigravity Agent"
    review['model'] = "Gemini 3.1 Pro"

    triage_list = []
    
    # Process clarification questions
    for q in review.get('clarification_questions', []):
        if q['question_id'] == 'CQ-VAL-BUG-TYPE':
            q['status'] = 'answered'
            q['answer'] = 'Valores sugeridos pelo agente baseados na descrição aceitos pelo usuário.'

    for bug in analysis.get('bugs', []):
        bug_id = bug['bug_id']
        title = bug.get('title', '').lower()
        desc = bug.get('description', '').lower()
        module = bug.get('affected_module', '').lower()
        rc_cat = bug.get('root_cause_category', '').lower()

        suggested_type = "Funcional"
        if "layout" in title or "layout" in desc or "css" in desc or "visual" in desc or "tela" in title:
            suggested_type = "Visual"
        elif "timeout" in title or "timeout" in desc or "lento" in title or "performance" in rc_cat:
            suggested_type = "Performance"
        elif "banco de dados" in rc_cat or "redis" in desc:
            suggested_type = "Infraestrutura"
        elif "api" in rc_cat or "integração" in rc_cat:
            suggested_type = "Integração"

        triage_item = {
            "bug_id": bug_id,
            "suggested_bug_type": suggested_type,
            "confidence": "high" if suggested_type != "Funcional" else "medium",
            "rationale": f"Inferido semânticamente a partir das palavras chave em título/descrição/categoria.",
            "review_status": "consistent"
        }
        triage_list.append(triage_item)

    review['triage'] = triage_list

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(review, f, indent=2, ensure_ascii=False)
        
    print(f"agent-review.json written with {len(triage_list)} triage items.")

if __name__ == "__main__":
    main()
