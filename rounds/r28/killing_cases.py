"""Check the limited natal premises documented in Ziping Zhenquan's 偏官 chapter."""

from itertools import pairwise, product

from lunar_python.util import LunarUtil
from open_birth_chart import bazi_engine as bazi

from rounds.r21.officer_cases import POSITIONS, RESOURCE, WEALTH, read_pillars


OUTPUT = {"食神", "伤官"}


def inspect(pillars):
    natal = read_pillars(pillars)
    day = natal["day"][0]
    month_branch = natal["month"][1]
    ten_gods = {stem: LunarUtil.SHI_SHEN[day + stem] for stem in bazi.GAN}
    visible = {i: natal[name][0] for i, name in enumerate(POSITIONS) if name != "day"}
    hidden = {name: LunarUtil.ZHI_HIDE_GAN[pillar[1]] for name, pillar in natal.items()}
    month_hidden = hidden["month"]
    visible_roles = {i: ten_gods[stem] for i, stem in visible.items()}
    month_killings = [stem for stem in month_hidden if ten_gods[stem] == "七杀"]
    month_context = any(stem == month_hidden[0] or stem in visible.values() for stem in month_killings)
    food = [i for i, role in visible_roles.items() if role == "食神"]
    outputs = [i for i, role in visible_roles.items() if role in OUTPUT]
    wealth = [i for i, role in visible_roles.items() if role in WEALTH]
    resource = [i for i, role in visible_roles.items() if role in RESOURCE]
    officers = [i for i, role in visible_roles.items() if role == "正官"]
    visible_killings = [stem for i, stem in visible.items() if visible_roles[i] == "七杀"]

    food_roots = {visible[i]: [name for name, stems in hidden.items() if visible[i] in stems] for i in food}
    all_branch_food_controlled_by_resource = any(
        bazi.control(visible[r], f) and len(roots) == 4 for r in resource for f, roots in food_roots.items()
    )
    same_month_resource = [visible[i] for i in resource if visible[i] in month_hidden]
    same_month_killings = [stem for stem in visible_killings if stem in month_killings]

    chain = [
        (POSITIONS[w], POSITIONS[r], POSITIONS[o], k, visible_roles[o])
        for w, r, o, k in product(wealth, resource, outputs, month_killings)
        if bazi.control(visible[w], visible[r]) and bazi.control(visible[r], visible[o]) and bazi.control(visible[o], k)
    ]
    adjacent_officer_control = [
        (POSITIONS[o], POSITIONS[k]) for left, right in pairwise(range(len(POSITIONS)))
        for o, k in ((left, right), (right, left))
        if k in officers and visible_roles.get(o) == "伤官" and bazi.control(visible[o], visible[k])
    ]
    officer_branch_clash = [
        POSITIONS[i] for i in officers if bazi.branch_clashes(natal[POSITIONS[i]][1], month_branch)
    ]
    hidden_resource = {
        name: [stem for stem in stems if ten_gods[stem] in RESOURCE] for name, stems in hidden.items()
    }
    branch_blades = [
        name for name, pillar in natal.items()
        if bazi.GAN.index(day) % 2 == 0 and bazi.growth(day, pillar[1]) == "帝旺"
    ]
    no_output = not outputs and all(ten_gods[stem] not in OUTPUT for stems in hidden.values() for stem in stems)
    branches = {pillar[1] for pillar in natal.values()}

    conditions = {
        "食神制杀前提": month_context and bool(food) and not wealth and not resource,
        "食重透印的可核部分": bool(visible_killings) and all_branch_food_controlled_by_resource,
        "杀印同通月令": bool(same_month_killings and same_month_resource),
        "财印食伤制化链": month_context and bool(chain),
        "寅亥化印与透财前提": month_branch == "亥" and month_context and "寅" in branches
        and bool(wealth) and any(bazi.element(visible[i]) == "木" for i in resource),
        "伤官制官留月令杀前提": month_context and bool(adjacent_officer_control),
        "冲月令杀留透官前提": month_context and bool(officer_branch_clash),
        "无食伤而见刃与藏印": month_context and no_output and bool(branch_blades) and any(hidden_resource.values()),
    }
    return {
        "conditions": conditions,
        "visible_stems": {POSITIONS[i]: {"stem": stem, "role": visible_roles[i]} for i, stem in visible.items()},
        "month_hidden_stems": {stem: ten_gods[stem] for stem in month_hidden},
        "month_killing_context": month_context,
        "visible_wealth_precedes_food": any(w < f for w in wealth for f in food),
        "visible_killings_exact_in_month": same_month_killings,
        "visible_resource_exact_in_month": same_month_resource,
        "visible_killings_same_element_roots_in_month": {
            stem: [h for h in month_hidden if bazi.element(stem) == bazi.element(h)] for stem in visible_killings
        },
        "food_root_positions": food_roots,
        "finances_resource_output_killing_links": chain,
        "strict_food_chain": any(link[-1] == "食神" for link in chain),
        "adjacent_officer_control": adjacent_officer_control,
        "officer_branch_clash": officer_branch_clash,
        "blade_positions": branch_blades,
        "hidden_resource": {name: stems for name, stems in hidden_resource.items() if stems},
        "no_visible_or_hidden_output": no_output,
        "strength_or_transformation_adjudicated": False,
    }
