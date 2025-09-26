from __future__ import annotations

from typing import Any, Dict, List

from playwright.async_api import Page


async def capture_interactive_nodes(page: Page) -> List[Dict[str, Any]]:
    """Snapshot inputs/buttons/selects/textarea nodes with contextual metadata."""

    raw_nodes: List[Dict[str, Any]] = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll('input, button, textarea, select')).map(el => {
            const attrs = {};
            for (const name of el.getAttributeNames()) {
                attrs[name] = el.getAttribute(name);
            }
            const ancestorsDetailed = [];
            let depth = 0;
            let current = el.parentElement;
            while (current && depth < 4) {
                const text = (current.innerText || '').trim();
                ancestorsDetailed.push({
                    depth,
                    text: text ? text.slice(0, 160) : '',
                    tag: current.tagName.toLowerCase(),
                    classes: Array.from(current.classList),
                });
                current = current.parentElement;
                depth += 1;
            }
            const siblingTexts = [];
            const prev = el.previousElementSibling;
            if (prev) {
                const text = (prev.innerText || '').trim();
                if (text) siblingTexts.push({ position: 'prev', text: text.slice(0, 160) });
            }
            const next = el.nextElementSibling;
            if (next) {
                const text = (next.innerText || '').trim();
                if (text) siblingTexts.push({ position: 'next', text: text.slice(0, 160) });
            }
            const form = el.form;
            const labels = el.labels ? Array.from(el.labels).map(label => label.innerText.trim()).filter(Boolean) : [];
            const nthOfType = (() => {
                let i = 1;
                let sibling = el.previousElementSibling;
                while (sibling) {
                    if (sibling.tagName === el.tagName) {
                        i += 1;
                    }
                    sibling = sibling.previousElementSibling;
                }
                return i;
            })();
            const sameTagCount = (() => {
                if (!el.parentElement) return 1;
                return Array.from(el.parentElement.children).filter(s => s.tagName === el.tagName).length || 1;
            })();
            return {
                tag: el.tagName.toLowerCase(),
                type: el.type || null,
                attrs,
                labels,
                role: el.getAttribute('role') || null,
                ariaLabel: el.getAttribute('aria-label') || null,
                ariaDescribedby: el.getAttribute('aria-describedby') || null,
                innerText: (el.innerText || '').trim(),
                textContent: (el.textContent || '').trim(),
                ancestorsDetailed,
                siblingTexts,
                formClasses: form ? Array.from(form.classList) : [],
                formId: form ? form.id : null,
                formAction: form ? form.getAttribute('action') : null,
                nthOfType,
                sameTagCount,
            };
        })
        """
    )

    return raw_nodes
