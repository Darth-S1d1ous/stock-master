### Class Stucture
```text
InvestmentThesis
        │
        └── ThesisCondition
                  │
                  └── RuleEvaluation
                            │
                            └── DomainEvent
                                  ├── EventEvidence
                                  └── EventFeedback
```

### Example
- InvestmentThesis: The valuation of AAPL cannot detach significantly from its fundamentals
- ThesisCondidion: PE ratio is 20% higher than the last snapshot
- RuleEvaluation: 
    - current PE 34.6
    - last PE 27.8
    - change 24.46%
    - matched = True
- DomainEvent: AAPL PE increase is larger than threshold
- EventEvidence: fundamental snapshot, calculation result
- EventFeedback: user marks as "valuable"
