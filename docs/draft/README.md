# Working Templates Directory

This directory contains working templates and draft documentation for the Anvil project. It serves as a staging area for documentation that is under development, review, or refinement before being moved to the main documentation structure.

## Purpose

The `/docs/draft/` directory is designed to:

- **Store work-in-progress documentation** that is not yet ready for publication
- **Provide a collaborative space** for authors to draft and iterate on content
- **Maintain version control** of documentation changes before they are finalized
- **Enable peer review** and feedback collection on upcoming documentation

## Directory Structure

```
docs/draft/
├── README.md                    # This file - directory overview
├── 02.00_Anvil_Neovim_Configuration_Framework.md  # Example draft document
└── [additional-draft-files].md  # Other working templates
```

## Guidelines for Use

### When to Use This Directory

- Creating new documentation that requires multiple revisions
- Documentation that needs team review before publishing
- Experimental or exploratory content
- Templates that may be reused across multiple documents

### File Naming Convention

Follow the established naming pattern from the main documentation:
- Use numerical prefix for ordering (e.g., `02.00_`, `02.01_`)
- Use descriptive titles with underscores instead of spaces
- Include version numbers when applicable
- End with `.md` extension

Example: `02.00_Anvil_Neovim_Configuration_Framework.md`

### Content Standards

- All draft documents should follow the established markdown format
- Include appropriate headers, sections, and formatting
- Add draft status indicators when necessary
- Document any dependencies or prerequisites

## Workflow

1. **Creation**: Start new documentation in this directory
2. **Development**: Iteratively improve and refine content
3. **Review**: Share with team members for feedback
4. **Finalization**: Complete and polish the documentation
5. **Migration**: Move to appropriate location in `/docs/content/` when ready

## Status Indicators

Consider adding status badges to draft documents:

- `[DRAFT]` - Initial version, work in progress
- `[REVIEW]` - Ready for team review
- `[BETA]` - Feature-complete but needs testing
- `[FINAL]` - Ready for migration to main docs

## Moving to Main Documentation

When a draft is complete:

1. Remove any draft status indicators
2. Ensure all links and references are correct
3. Update any cross-references in other documents
4. Move file to appropriate location in `/docs/content/`
5. Update any table of contents or index files

## Collaboration

This directory is intended for collaborative work. Team members should:

- Comment on draft documents using version control
- Provide constructive feedback through pull requests
- Follow the established style guidelines
- Communicate about upcoming changes or reviews

---

**Note**: This directory is part of the iterative documentation process. Content here is subject to change and may not represent the final state of the Anvil project documentation.
