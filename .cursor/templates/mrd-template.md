# AAMAD Deep Research / Market Research Document (MRD) Template

## Context & Instructions
You are conducting comprehensive research for developing a production-ready multi-agent system.
Base recommendations on evidence. Treat the selected runtime (`AAMAD_TARGET_RUNTIME`) as an implementation choice for the generated MVP, not as the AAMAD methodology itself.
When the project is internal or personal and market research is skipped, do not force this document; record the skip under Assumptions in the PRD instead.

## Research Query Structure

**Primary Focus**: [INSERT YOUR MULTI-AGENT SYSTEM CONCEPT HERE]  
**Example**: "Customer Support AI Agent System for SaaS companies"  
**Selected Runtime** (optional for research; required later in Build): [crewai | claude-agent-sdk | cursor-sdk]

## Research Dimensions — Investigate All Areas Below

### 1. Market Analysis & Opportunity Assessment

- **Market Size**: Current and projected market size for this application domain  
- **Growth Trends**: 3-year growth projections and driving factors  
- **Market Gaps**: Specific unmet needs in current solutions  
- **Target Audience**: Detailed personas, pain points, and willingness to pay  
- **Business Case**: ROI potential and value proposition validation  
- **Competitive Landscape**: Direct and indirect competitors with feature analysis

### 2. Technical Feasibility & Requirements Analysis

- **Runtime Capabilities**: Fit of the selected (or candidate) runtime adapters for this use case  
- **Agent Architecture Patterns**: Proven multi-agent patterns for this domain  
- **Integration Requirements**: APIs, databases, and third-party services needed  
- **Scalability Considerations**: Performance bottlenecks and scaling strategies  
- **Technical Risks**: Implementation challenges and mitigation approaches  
- **Infrastructure Needs**: Cloud services, compute requirements, and cost projections

### 3. User Experience & Workflow Analysis

- **User Journey Mapping**: End-to-end interaction flows with the multi-agent system  
- **Interface Requirements**: UI/UX needs for human-agent interaction  
- **Automation Opportunities**: Tasks suitable for full vs partial automation  
- **Human-in-the-Loop**: When and how human oversight is required  
- **Success Metrics**: Measurable outcomes and KPIs for system effectiveness  
- **User Adoption Factors**: Barriers and enablers for user acceptance

### 4. Production & Operations Requirements

- **Deployment Architecture**: Cloud infrastructure and deployment strategies  
- **Monitoring & Observability**: Essential metrics and logging requirements  
- **Security Considerations**: Data protection, access control, and compliance needs  
- **Maintenance & Updates**: System update patterns and version management  
- **Cost Structure**: Development, deployment, and operational cost breakdown  
- **Risk Assessment**: Operational risks and business continuity planning

### 5. Innovation & Differentiation Analysis

- **Unique Value Propositions**: How this solution differs from existing approaches  
- **Emerging Technologies**: Relevant AI/ML advances and integration opportunities  
- **Patent Landscape**: Existing patents and IP considerations  
- **Future Trends**: Technology and market evolution affecting long-term viability  
- **Partnership Opportunities**: Strategic alliances and integration possibilities  
- **Monetization Strategies**: Revenue models and pricing approaches

## Output Format Requirements

### Executive Summary (2-3 paragraphs)

- **Market Opportunity**: Size, growth, and business case  
- **Technical Feasibility**: Implementation complexity and success probability  
- **Recommended Approach**: Strategic direction based on research findings

### Detailed Findings by Dimension

For each of the 5 research dimensions above:

- **Key Insights**: 3-5 critical findings with supporting evidence  
- **Data Points**: Specific metrics, statistics, and quantitative evidence  
- **Source Citations**: Research sources and publication dates  
- **Implications**: How findings impact system design and business strategy

### Critical Decision Points

- **Go/No-Go Factors**: Essential requirements for project viability  
- **Technical Architecture Choices**: Runtime and technology recommendations  
- **Market Positioning**: Optimal target market and value proposition  
- **Resource Requirements**: Team, timeline, and budget implications

### Risk Assessment Matrix

- **High Risk**: Critical threats requiring immediate attention  
- **Medium Risk**: Important considerations for planning  
- **Low Risk**: Minor issues to monitor during development

### Actionable Recommendations

- **Immediate Next Steps**: Actions to take within 48 hours  
- **Short-term Priorities**: Development focus for next 30 days  
- **Long-term Strategy**: 6-12 month roadmap based on findings

## Research Quality Requirements

- Cite at least 15-20 authoritative sources  
- Include recent data (within 18 months when possible)  
- Provide quantitative evidence for all major claims  
- Cross-reference findings across multiple sources  
- Identify conflicting information and provide analysis

## Sources

- List research sources, URLs, and dates

## Assumptions

- Gaps filled by inference; market-skip rationale if sections were abbreviated

## Open Questions

- Unresolved items for stakeholder or architect resolution

## Audit

- Timestamp, persona id (`product-mgr`), action (`create-mrd`), optional resolved `AAMAD_TARGET_RUNTIME`
