"""Read selections with OS accessibility APIs; never simulate copy or change the clipboard."""
import os
import re
import sys
from dataclasses import dataclass

from word_engine import MAX_SELECTION, WORD, valid_selection


@dataclass(frozen=True)
class Selection:
    selected: str
    word: str
    context: str = ""


def from_neighbors(selected, before, after):
    selected = selected.strip()
    if not valid_selection(selected):
        return None
    if not WORD.fullmatch(selected) or len(selected) > 80:
        return Selection(selected, selected, before[-220:] + "[[" + selected + "]]" + after[:220])
    # A selected word next to a hyphen is a separate selection.  Do not
    # silently turn "powered" in "LLMs-powered" into the entire compound.
    left = re.search(r"[A-Za-z'’]+$", before)
    right = re.match(r"[A-Za-z'’]+", after)
    prefix = left.group(0) if left else ""
    suffix = right.group(0) if right else ""
    candidate = prefix + selected + suffix
    if WORD.fullmatch(candidate) and len(candidate) <= 80:
        word = candidate
        before = before[:-len(prefix)] if prefix else before
        after = after[len(suffix):]
    else:
        word = selected
    context = before[-220:] + "[[" + word + "]]" + after[:220]
    return Selection(selected, word, context)


def from_value(selected, text):
    if not isinstance(text, str) or len(text) > 200000 or not selected:
        return Selection(selected, selected) if valid_selection(selected) else None
    start = text.find(selected)
    if start < 0 or text.find(selected, start + 1) >= 0:
        return Selection(selected, selected) if valid_selection(selected) else None
    return from_neighbors(selected, text[max(0, start - 300):start], text[start + len(selected):start + len(selected) + 300])


def windows_selection(x, y, prefer_focus=False):
    import uiautomation as uia
    with uia.UIAutomationInitializerInThread():
        starts = []
        try:
            focused = uia.GetFocusedControl()
        except Exception:
            focused = None
        if prefer_focus:
            if focused:
                starts.append(focused)
        else:
            try:
                pointed = uia.ControlFromPoint(x, y)
            except Exception:
                pointed = None
            if pointed:
                starts.append(pointed)
            # A drag in one application must not query a stale selection in another.
            try:
                if pointed and focused and pointed.ProcessId == focused.ProcessId:
                    starts.append(focused)
            except Exception:
                pass
        for start in starts:
            control = start
            # Browser pages can have many nested layout and heading nodes
            # between a text fragment and the document that exposes selection.
            for _ in range(40):
                if control is None:
                    break
                try:
                    if control.ProcessId == os.getpid() or control.IsPassword:
                        break
                    pattern = control.GetPattern(uia.PatternId.TextPattern)
                    ranges = pattern.GetSelection() if pattern else []
                    if len(ranges) == 1:
                        target = ranges[0]
                        selected = target.GetText(MAX_SELECTION + 1).strip()
                        if selected and not valid_selection(selected):
                            # Do not fall back to an ancestor's stale English selection.
                            return None
                        if not selected:
                            control = control.GetParentControl()
                            continue
                        try:
                            left = target.Clone()
                            left.MoveEndpointByRange(uia.TextPatternRangeEndpoint.End, target, uia.TextPatternRangeEndpoint.Start, waitTime=0)
                            left.MoveEndpointByUnit(uia.TextPatternRangeEndpoint.Start, uia.TextUnit.Character, -220, waitTime=0)
                            right = target.Clone()
                            right.MoveEndpointByRange(uia.TextPatternRangeEndpoint.Start, target, uia.TextPatternRangeEndpoint.End, waitTime=0)
                            right.MoveEndpointByUnit(uia.TextPatternRangeEndpoint.End, uia.TextUnit.Character, 220, waitTime=0)
                            return from_neighbors(selected, left.GetText(220), right.GetText(220))
                        except Exception:
                            return Selection(selected, selected)
                except Exception:
                    pass
                try:
                    control = control.GetParentControl()
                except Exception:
                    break
    return None


def mac_selection():
    import ApplicationServices as ax
    if not ax.AXIsProcessTrusted():
        return None
    system = ax.AXUIElementCreateSystemWide()
    error, element = ax.AXUIElementCopyAttributeValue(system, ax.kAXFocusedUIElementAttribute, None)
    if error or element is None:
        return None
    try:
        error, pid = ax.AXUIElementGetPid(element, None)
        if not error and pid == os.getpid():
            return None
    except Exception:
        pass
    _, role = ax.AXUIElementCopyAttributeValue(element, ax.kAXRoleAttribute, None)
    _, subrole = ax.AXUIElementCopyAttributeValue(element, ax.kAXSubroleAttribute, None)
    if str(role) == "AXSecureTextField" or str(subrole) == "AXSecureTextField":
        return None
    error, value = ax.AXUIElementCopyAttributeValue(element, ax.kAXSelectedTextAttribute, None)
    selected = str(value or "").strip() if not error else ""
    if not valid_selection(selected):
        return None
    try:
        error, full = ax.AXUIElementCopyAttributeValue(element, ax.kAXValueAttribute, None)
        if not error and isinstance(full, str):
            return from_value(selected, full)
    except Exception:
        pass
    return Selection(selected, selected)


def get_selection(x, y, prefer_focus=False):
    try:
        if sys.platform == "win32":
            return windows_selection(int(x), int(y), prefer_focus)
        if sys.platform == "darwin":
            return mac_selection()
    except Exception:
        return None
    return None
