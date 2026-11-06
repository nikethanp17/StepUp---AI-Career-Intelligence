from sentence_transformers import SentenceTransformer, util
m = SentenceTransformer('all-MiniLM-L6-v2')

related = [("azure","aws"), ("gcp","aws"), ("mysql","postgresql"), ("react","angular"),
           ("javascript","typescript"), ("docker","kubernetes"), ("html","css")]
unrelated = [("python","figma"), ("react","sql"), ("docker","wireframing"),
             ("aws","user research"), ("java","figma")]

def sim(a, b):
    return util.cos_sim(m.encode(a), m.encode(b)).item()

print("RELATED pairs")
for a, b in related:
    print(f"  {a:12} vs {b:14} {sim(a,b):.2f}")
print("UNRELATED pairs")
for a, b in unrelated:
    print(f"  {a:12} vs {b:14} {sim(a,b):.2f}")

# also try phrase form, which often scores more reliably than single words
print("PHRASE form (related)")
for a, b in related:
    print(f"  {a:12} vs {b:14} {sim('experience with '+a, 'experience with '+b):.2f}")