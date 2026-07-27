import json

def main():
    output_path = r"C:\Users\Acer\Documents\lab-lucas\rca-agent-lab\.rca-work\bugs-app-delivery-kpi-351d5db0b672\agent-review.json"

    with open(output_path, 'r', encoding='utf-8') as f:
        review = json.load(f)

    # 1. Create Evidence objects
    evidence_list = [
        {
            "evidence_id": "EV-1008",
            "source_type": "dev_note",
            "source_ref": "DELIV-1008",
            "bug_id": "DELIV-1008",
            "excerpt": "Problema reproduzido via k6 forçando concorrência",
            "reliability": "high",
            "reliability_basis": "Reportado diretamente pelo QA/Dev no ticket"
        },
        {
            "evidence_id": "EV-1013",
            "source_type": "dev_note",
            "source_ref": "DELIV-1013",
            "bug_id": "DELIV-1013",
            "excerpt": "Problema reproduzido via k6 forçando concorrência",
            "reliability": "high",
            "reliability_basis": "Reportado diretamente pelo QA/Dev no ticket"
        },
        {
            "evidence_id": "EV-1003",
            "source_type": "description",
            "source_ref": "DELIV-1003",
            "bug_id": "DELIV-1003",
            "excerpt": "Pequena quebra de layout de CSS (flexbox)",
            "reliability": "high",
            "reliability_basis": "Descrição do problema"
        },
        {
            "evidence_id": "EV-1010",
            "source_type": "description",
            "source_ref": "DELIV-1010",
            "bug_id": "DELIV-1010",
            "excerpt": "Pequena quebra de layout de CSS (flexbox)",
            "reliability": "high",
            "reliability_basis": "Descrição do problema"
        }
    ]
    review['evidence'] = evidence_list

    # 2. Update references in insights, hypotheses, actions, narrative
    def replace_ids(obj_list):
        for obj in obj_list:
            if 'evidence_ids' in obj:
                obj['evidence_ids'] = [ref.replace('DELIV-', 'EV-') for ref in obj['evidence_ids']]
            if 'supporting_evidence_ids' in obj:
                obj['supporting_evidence_ids'] = [ref.replace('DELIV-', 'EV-') for ref in obj['supporting_evidence_ids']]
            if 'counter_evidence_ids' in obj:
                obj['counter_evidence_ids'] = [ref.replace('DELIV-', 'EV-') for ref in obj['counter_evidence_ids']]

    replace_ids(review.get('insights', []))
    replace_ids(review.get('hypotheses', []))
    replace_ids(review.get('actions', []))

    if 'narrative' in review:
        replace_ids(review['narrative'].get('methodology_reviews', []))
        replace_ids(review['narrative'].get('root_cause_signal_reviews', []))
        replace_ids(review['narrative'].get('cluster_gap_reviews', []))

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(review, f, indent=2, ensure_ascii=False)
        
    print(f"agent-review.json evidence fixed.")

if __name__ == "__main__":
    main()
