#pragma once
// Shared production camera composition, included inside the implementation
// namespace. The explicit prototype build adds evidence recording only.
namespace camera_composition
{
struct Value { double xyz[3]{}; std::uint8_t type{1}; std::uint8_t padding[7]{}; };
static_assert(sizeof(Value) == 32);
using Handler = void (*)(void*, const Value*);
using Modifier = Value* (*)(void*, Value*, void*, const Value*, float);
enum Reason : std::uint32_t { ok, no_dispatch, stale, unsupported, mappings, unobserved,
    inactive, mode, identity, cold, duplicate, nested, changed, overflow, output_mismatch };
enum Event : std::uint32_t { rejected=1, begin, output, finish, released };
enum class InventoryReason : std::uint32_t { none, maps_read, maps_null, count_read, count_negative,
    count_limit, action_read, source_axis, source_unknown, triggers_read, triggers_nonempty,
    key_read, modifiers_read, modifier_count_read, modifier_count_negative, modifier_count_limit,
    flags_read, candidate_invalid, candidate_instance, candidate_axis, candidate_source,
    orphan_invalid, orphan_before, orphan_after, orphan_alignment, action_missing, digital_candidate, limit };
static_assert(static_cast<unsigned>(InventoryReason::limit)<=32);
struct InventoryDiagnostic
{
    std::uint64_t maps{}, mapping{}, mapping_action{}, key{}, modifiers{}, layout{},
        candidate_mapping{}, candidate_action{}, candidate_instance{}, mouse_x{}, mouse_y{}, gamepad_x{}, gamepad_y{};
    std::uint32_t subreason{}, read_mask{};
    std::int32_t count{}, mapping_index{-1}, trigger_count{}, modifier_count{}, candidate_index{-1};
    std::uint32_t candidate_count{}, source{}, source_axis{}, candidate_valid{}, candidate_source{}, candidate_axis{}, flags{};
};
static_assert(sizeof(InventoryDiagnostic)==160);
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
#include "CameraJournal.hpp"
#endif
bool finite(double v) noexcept
{
    std::uint64_t b{}; std::memcpy(&b,&v,8);
    return (b & 0x7ff0000000000000ULL) != 0x7ff0000000000000ULL;
}
double magnitude(double v) noexcept { return v < 0 ? -v : v; }
unsigned ai(Axis a) noexcept { return a == Axis::X ? 0 : 1; }
unsigned si(Source s) noexcept { return s == Source::Mouse ? 0 : 1; }
bool scalar(const Value& v) noexcept
{ return v.type==1 && finite(v.xyz[0]) && v.xyz[1]==0 && v.xyz[2]==0 && magnitude(v.xyz[0]) < 1e20; }

struct ObjectId { std::int32_t index{}, serial{}; bool operator==(const ObjectId&) const = default; };
// Same chunk/entry/serial/flags layout as shipping weak resolution 0x141126290.
// Read only: do not allocate weak serials or call back into the game.
bool object_id(const void* object, ObjectId& id) noexcept
{
    const auto p = reinterpret_cast<std::uintptr_t>(object);
    std::int32_t count{}; std::uintptr_t chunks{}, chunk{}, actual{}; std::uint32_t flags{};
    if (!read(p+0xC,id.index) || id.index<0 || !read(base+0x9112A84,count) || id.index>=count ||
        !read(base+0x9112A70,chunks) || !chunks ||
        !read(chunks+8*(static_cast<unsigned>(id.index)>>16),chunk) || !chunk) return false;
    const auto item=chunk+24*(static_cast<unsigned>(id.index)&0xffff);
    return read(item,actual) && actual==p && read(item+8,flags) && !(flags&0x30200000) &&
        read(item+16,id.serial) && id.serial>0;
}
bool empty(std::uintptr_t header) noexcept
{ int n{}; return read(header+8,n) && n==0; }
bool supported(const void* instance, const void*& action) noexcept
{
    const auto p=reinterpret_cast<std::uintptr_t>(instance);
    return action_info(instance,action) && empty(p+0x18) && empty(p+0x28);
}
struct Candidate { const void* action{}; const void* instance{}; std::uintptr_t mapping{};
    Winner source{}; Value value{}; bool valid{}; };
struct Table
{
    struct Delivery { void* receiver{}; const void* action{}; Axis axis{}; } deliveries[8]{};
    Generation generation{}; Candidate entries[64]{}; unsigned count{}; bool bad{}, delivering{};
    unsigned delivery_count{};
    void sync() noexcept
    {
        if (generation.number!=provenance.generation.number || generation.owner!=provenance.generation.owner ||
            generation.frame!=provenance.generation.frame)
        { generation=provenance.generation; count=0; delivery_count=0; bad=false; delivering=false; }
    }
};
constinit thread_local Table table{};
struct Bank
{
    void* receiver{}; ObjectId receiver_id{}, owner_id{}; const void* owner{};
    std::uint64_t generation{}, layout{};
    float latest[2][2]{}; // source, axis; only delivered history, never next-axis preloading
    bool known[2]{};
    std::uint64_t delivered[2]{};
};
constinit thread_local Bank bank{};
struct Run
{
    Dispatch* dispatch{}; Generation generation{}; void* receiver{}; Axis axis{}; Source source{};
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    std::uint64_t call{}; double mouse{},stick{},input{}; bool logging{};
#endif
    bool tail{},interrupted{},good{true};
    unsigned outputs[2]{};
};
constinit thread_local Run* active{};
bool current(const Run& r) noexcept
{ return enabled.load(std::memory_order_acquire) && current_dispatch==r.dispatch && provenance.matches(r.generation); }
bool source_override(Axis axis, std::uint8_t& value) noexcept
{
    if (!active || active->axis!=axis || !current(*active)) return false;
    value = active->source==Source::Gamepad ? 1 : 0; return true;
}
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
Record row(Event event, Reason reason=ok) noexcept
{
    Record r{}; r.event=event; r.reason=reason;
    if (auto* d=current_dispatch)
    { r.generation=d->generation.number; r.frame=d->generation.frame; r.owner=reinterpret_cast<std::uintptr_t>(d->generation.owner);
      r.action=reinterpret_cast<std::uintptr_t>(d->action); r.instance=reinterpret_cast<std::uintptr_t>(d->instance); }
    if (active)
    { r.call=active->call; r.receiver=reinterpret_cast<std::uintptr_t>(active->receiver); r.axis=static_cast<unsigned>(active->axis);
      r.source=static_cast<unsigned>(active->source); r.mouse=active->mouse; r.stick=active->stick; r.input=active->input; }
    return r;
}
#endif
void reject([[maybe_unused]] Reason reason, [[maybe_unused]] void* receiver,
            [[maybe_unused]] Axis axis, [[maybe_unused]] const InventoryDiagnostic* detail=nullptr) noexcept
{
    bank={};
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    if (reason==mappings && detail)
    {
        const auto mask=1U<<detail->subreason;
        if (!(inventory_seen[ai(axis)].fetch_or(mask,std::memory_order_relaxed)&mask))
        { auto r=row(rejected,reason); r.receiver=reinterpret_cast<std::uintptr_t>(receiver);
          r.axis=static_cast<unsigned>(axis); r.inventory=*detail; record(r); }
        return;
    }
    const auto mask=1U<<reason;
    if (!(rejection_seen.fetch_or(mask,std::memory_order_relaxed)&mask))
    { auto r=row(rejected,reason); r.receiver=reinterpret_cast<std::uintptr_t>(receiver); r.axis=static_cast<unsigned>(axis); record(r); }
#endif
}
Value* modify(void* owner, Value* out, void* modifiers, const Value* in, float delta,
              std::uintptr_t frame, void* instance)
{
    // Modifier callback can recurse. Capture the generation BEFORE the call.
    std::uintptr_t evaluation{}, caller{}, key{}, triggers{}, frame_action{};
    const bool frame_ok=read(frame+0x37,evaluation) && read(frame+0x3F,caller) && read(frame+0x1F,key) &&
        read(frame+0x7F,triggers) && read(frame+0x4F,frame_action);
    const auto token=frame_ok ? provenance.capture(owner,evaluation) : Generation{};
    auto* result=reinterpret_cast<Modifier>(base+0x3927920)(owner,out,modifiers,in,delta);
    if (!enabled.load(std::memory_order_acquire) || !provenance.matches(token)) return result;
    table.sync();
    const void* action{};
    if (!read(reinterpret_cast<std::uintptr_t>(instance),action) || !action) { table.bad=true; return result; }
    // Keep unknown/foreign records as rejection evidence for the affected action.
    Candidate c{}; c.action=action; c.instance=instance; c.mapping=key>=0x28 ? key-0x28 : 0;
    c.source=classify(key);
    const void* checked{};
    c.valid=frame_ok && caller==base+sites::mapping_return && frame_action==reinterpret_cast<std::uintptr_t>(action) &&
        c.mapping==triggers && reinterpret_cast<std::uintptr_t>(modifiers)==c.mapping+0x10 &&
        supported(instance,checked) && checked==action && empty(triggers) && read(reinterpret_cast<std::uintptr_t>(out),c.value) &&
        scalar(c.value) && c.source.source!=Source::Unknown;
    if (table.delivering || table.count==std::size(table.entries)) { table.bad=true; return result; }
    for (unsigned i=0;i<table.count;++i)
        if (table.entries[i].mapping==c.mapping && table.entries[i].action==action) c.valid=false;
    table.entries[table.count++]=c;
    return result;
}

struct Pair { double values[2]{}; bool seen[2]{}; std::uint64_t layout{1469598103934665603ULL};
    InventoryDiagnostic diagnostic{}; };
// Keep SEH inside a separate function: an inlined faulting read inside the
// diagnostic lambdas can leave volatile closure registers clobbered on recovery.
template <typename T> __declspec(noinline) bool inventory_read(std::uintptr_t p, T& value) noexcept
{ return read(p,value); }
bool digital_key(std::uintptr_t key) noexcept
{
    // Same full FKeyDetails identity/type proof as movement classification.
    // Only inspect already-cached metadata; never resolve it through game calls.
    std::uint64_t name{}, details_name{}; std::uintptr_t details{}; std::uint8_t type{};
    return inventory_read(key,name) && name && inventory_read(key+8,details) && details &&
        inventory_read(details,details_name) && details_name==name &&
        inventory_read(details+0x42,type) && type==0;
}
bool inventory(const Dispatch& d, Axis axis, Pair& pair) noexcept
{
    auto& e=pair.diagnostic;
    const auto o=reinterpret_cast<std::uintptr_t>(d.generation.owner);
    // Successful guard reads are retained. Extra, guarded reads happen only on
    // rejection, never influence eligibility, and have explicit validity bits.
    auto probe=[&](std::uintptr_t p, auto& value, unsigned bit) {
        if (inventory_read(p,value)) { e.read_mask|=1U<<bit; return true; } return false;
    };
    auto candidate_detail=[&](unsigned k) {
        const auto& c=table.entries[k]; e.candidate_index=static_cast<int>(k);
        e.candidate_mapping=c.mapping; e.candidate_action=reinterpret_cast<std::uintptr_t>(c.action);
        e.candidate_instance=reinterpret_cast<std::uintptr_t>(c.instance); e.candidate_valid=c.valid;
        e.candidate_source=static_cast<unsigned>(c.source.source); e.candidate_axis=static_cast<unsigned>(c.source.axis);
    };
    auto fail=[&](InventoryReason reason) {
        e.subreason=static_cast<unsigned>(reason); e.layout=pair.layout; e.candidate_count=table.count;
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
        // Rejection-only evidence sampling never participates in eligibility.
        if (!(e.read_mask&2)) probe(o+0x550,e.count,1);
        if (e.mapping_index>=0)
        {
            if (!(e.read_mask&4)) probe(e.mapping+0x20,e.mapping_action,2);
            if (!(e.read_mask&8)) probe(e.mapping+8,e.trigger_count,3);
            if (!(e.read_mask&16)) probe(e.mapping+0x28,e.key,4);
            if (!(e.read_mask&32)) probe(e.mapping+0x10,e.modifiers,5);
            if (!(e.read_mask&64)) probe(e.mapping+0x18,e.modifier_count,6);
            if (!(e.read_mask&128)) { std::uint8_t flags{}; if (probe(e.mapping+0x40,flags,7)) e.flags=flags; }
            if (e.candidate_index<0)
                for (unsigned k=0;k<table.count;++k)
                    if (table.entries[k].action==d.action && table.entries[k].mapping==e.mapping)
                    { candidate_detail(k); break; }
        }
        probe(base+sites::mouse_x,e.mouse_x,8); probe(base+sites::mouse_y,e.mouse_y,9);
        probe(base+sites::gamepad_x,e.gamepad_x,10); probe(base+sites::gamepad_y,e.gamepad_y,11);
#endif
        return false;
    };
    if (!probe(o+0x548,e.maps,0)) return fail(InventoryReason::maps_read);
    if (!e.maps) return fail(InventoryReason::maps_null);
    if (!probe(o+0x550,e.count,1)) return fail(InventoryReason::count_read);
    if (e.count<0) return fail(InventoryReason::count_negative);
    if (e.count>1024) return fail(InventoryReason::count_limit);
    const auto maps=e.maps; const auto count=e.count;
    auto hash=[&](std::uint64_t x) { pair.layout=(pair.layout^x)*1099511628211ULL; };
    hash(maps); hash(count);
    bool found=false;
    for (int i=0;i<count;++i)
    {
        const auto m=maps+0x50*i; const void* action{};
        e.mapping=m; e.mapping_index=i; e.mapping_action=0; e.read_mask&=3;
        e.key=0; e.modifiers=0; e.trigger_count=0; e.modifier_count=0; e.flags=0;
        e.source=0; e.source_axis=0;
        if (!probe(m+0x20,action,2)) return fail(InventoryReason::action_read);
        e.mapping_action=reinterpret_cast<std::uintptr_t>(action);
        if (action!=d.action) continue;
        found=true; const auto source=classify(m+0x28);
        const bool digital=source.source==Source::Unknown && digital_key(m+0x28);
        e.source=static_cast<unsigned>(digital?Source::Digital:source.source); e.source_axis=static_cast<unsigned>(source.axis);
        if (!digital && source.axis!=axis) return fail(InventoryReason::source_axis);
        if (!digital && source.source==Source::Unknown) return fail(InventoryReason::source_unknown);
        if (!probe(m+8,e.trigger_count,3)) return fail(InventoryReason::triggers_read);
        if (e.trigger_count!=0) return fail(InventoryReason::triggers_nonempty);
        if (!probe(m+0x28,e.key,4)) return fail(InventoryReason::key_read);
        if (!probe(m+0x10,e.modifiers,5)) return fail(InventoryReason::modifiers_read);
        if (!probe(m+0x18,e.modifier_count,6)) return fail(InventoryReason::modifier_count_read);
        if (e.modifier_count<0) return fail(InventoryReason::modifier_count_negative);
        if (e.modifier_count>64) return fail(InventoryReason::modifier_count_limit);
        std::uint8_t flags{};
        if (!probe(m+0x40,flags,7)) return fail(InventoryReason::flags_read);
        e.flags=flags;
        hash(m); hash(e.key); hash(e.modifiers); hash(e.modifier_count); hash(flags);
        // Inactive/skipped mappings have no candidate in this generation: zero,
        // never last frame's value. Any observed unsupported mapping poisons it.
        for (unsigned k=0;k<table.count;++k)
        {
            const auto& c=table.entries[k];
            if (c.action!=d.action || c.mapping!=m) continue;
            auto candidate_fail=[&](InventoryReason reason) { candidate_detail(k); return fail(reason); };
            // Digital alternatives remain in the structural/layout inventory,
            // but ANY observation (even zero/invalid) prevents composition.
            // Absence is usable only with the complete current table checked by camera().
            if (digital) return candidate_fail(InventoryReason::digital_candidate);
            if (!c.valid) return candidate_fail(InventoryReason::candidate_invalid);
            if (c.instance!=d.instance) return candidate_fail(InventoryReason::candidate_instance);
            if (c.source.axis!=axis) return candidate_fail(InventoryReason::candidate_axis);
            if (c.source.source!=source.source) return candidate_fail(InventoryReason::candidate_source);
            const auto s=si(source.source); const auto v=c.value.xyz[0];
            if (!pair.seen[s] || magnitude(v)>=magnitude(pair.values[s])) pair.values[s]=v;
            pair.seen[s]=true;
        }
    }
    for (unsigned k=0;k<table.count;++k)
    {
        const auto& c=table.entries[k];
        if (c.action!=d.action) continue;
        auto orphan_fail=[&](InventoryReason reason) {
            // No current mapping in the final candidate scan; don't report the
            // last unrelated row, or dereference an out-of-inventory candidate.
            e.mapping=0; e.mapping_action=0; e.mapping_index=-1; e.read_mask&=3;
            e.key=0; e.modifiers=0; e.trigger_count=0; e.modifier_count=0; e.flags=0;
            e.source=0; e.source_axis=0; candidate_detail(k); return fail(reason);
        };
        if (!c.valid) return orphan_fail(InventoryReason::orphan_invalid);
        if (c.mapping<maps) return orphan_fail(InventoryReason::orphan_before);
        if (c.mapping>=maps+0x50*count) return orphan_fail(InventoryReason::orphan_after);
        if ((c.mapping-maps)%0x50) return orphan_fail(InventoryReason::orphan_alignment);
    }
    if (!found)
    { e.mapping=0; e.mapping_action=0; e.mapping_index=-1; e.read_mask&=3; return fail(InventoryReason::action_missing); }
    return true;
}
bool ordinary(void* receiver, Generation generation) noexcept
{
    std::uint8_t paused{}, alternate{}, ignore{}; std::uintptr_t manager{}, vt{}, target{};
    const auto h=reinterpret_cast<std::uintptr_t>(receiver);
    return provenance.matches(generation) && read(generation.frame+0x558,paused) && !paused &&
        read(base+0x92CE6D0,manager) && manager && read(manager+0xB9+0x26,alternate) && !alternate &&
        read(h,vt) && read(vt+0x838,target) && target==base+0x30C8E30 && read(h+0x32A,ignore) && !ignore &&
        read(vt+0xD18,target) && target==base+0x3564E20 && read(vt+0xD10,target) && target==base+0x3563AB0;
}
void tail(void* h)
{
    if (active && active->receiver==h && current(*active)) { active->tail=true; return; }
    reinterpret_cast<void (*)(void*)>(base+0x4898A70)(h);
}
template <Axis A, Source S> void angular(void* h, float value)
{
    const auto offset=A==Axis::X ? 0x530 : 0x528;
    const auto slot=A==Axis::X ? 0xD18 : 0xD10;
    auto* r=active;
    const bool tracked=r && current(*r) && r->receiver==h && r->axis==A;
    double before{},after{};
    const bool before_ok=tracked && read(reinterpret_cast<std::uintptr_t>(h)+offset,before);
    auto target=(*reinterpret_cast<std::uintptr_t**>(h))[slot/8];
    // Keep exactly the native virtual call, including its gating and legacy scale.
    reinterpret_cast<void (*)(void*,float)>(target)(h,value);
    if (tracked)
    {
        const bool good=current(*r) && S==r->source && before_ok &&
            read(reinterpret_cast<std::uintptr_t>(h)+offset,after) && finite(before) && finite(after) && finite(value);
        ++r->outputs[si(S)]; r->good &= good && r->outputs[si(S)]==1;
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
        if (r->logging)
        { auto e=row(output,good?ok:output_mismatch); e.source=static_cast<unsigned>(S); e.target=target;
          e.angular=value; e.before=before; e.after=after; e.flags=good?1:0; record(e); }
#endif
    }
}

// Only temporary latest-axis fields are restored. Native stick gain fields are
// never replaced, reset each frame, or copied into a second history.
struct Samples
{
    float* fields; float saved[2];
    Run* run;
    Samples(void* h, Source source, unsigned axis, double value) :
        fields(reinterpret_cast<float*>(reinterpret_cast<std::uintptr_t>(h)+0xD64)), run(active)
    {
        std::memcpy(saved,fields,sizeof(saved));
        if (source==Source::Gamepad) std::memcpy(fields,bank.latest[1],sizeof(saved));
        fields[axis]=static_cast<float>(value);
    }
    ~Samples()
    {
        // A recursive camera/evaluation may have intentionally written new state.
        // Do not overwrite it with an outer snapshot on the way back out.
        if (!run->interrupted && provenance.matches(run->generation)) std::memcpy(fields,saved,sizeof(saved));
    }
};
struct Completion { bool done{}; ~Completion() { if (!done) bank={}; } };
template <Axis A> void camera(void* h, const Value* input)
{
    const auto original=reinterpret_cast<Handler>(base+(A==Axis::X ? sites::camera_x : sites::camera_y));
    auto fallback=[&](Reason reason, const InventoryDiagnostic* detail=nullptr) {
        reject(reason,h,A,detail); Scope mask(active,static_cast<Run*>(nullptr)); original(h,input); };
    if (active) { active->interrupted=true; active->good=false; fallback(nested); return; }
    auto* d=current_dispatch; Value delivered{}; const void* checked{};
    if (!enabled.load(std::memory_order_acquire) || !d) { fallback(no_dispatch); return; }
    table.sync();
    if (!provenance.matches(d->generation) || table.bad) { fallback(stale); return; }
    if (!supported(d->instance,checked) || checked!=d->action || !read(reinterpret_cast<std::uintptr_t>(input),delivered) ||
        !scalar(delivered)) { fallback(unsupported); return; }
    std::uint8_t event{}; Value instance_value{};
    if (!read(reinterpret_cast<std::uintptr_t>(d->instance)+0x13,event) || event!=1 || delivered.xyz[0]==0 ||
        !read(reinterpret_cast<std::uintptr_t>(d->instance)+0x38,instance_value) || delivered.xyz[0]!=instance_value.xyz[0])
    { fallback(inactive); return; }
    Pair pair{};
    if (!inventory(*d,A,pair)) { fallback(mappings,&pair.diagnostic); return; }
    const auto winner=current_winner(A);
    if ((winner.source!=Source::Mouse && winner.source!=Source::Gamepad) ||
        !pair.seen[si(winner.source)] || pair.values[si(winner.source)]!=delivered.xyz[0]) { fallback(unobserved); return; }
    if (!ordinary(h,d->generation)) { fallback(mode); return; }
    for (unsigned i=0;i<table.delivery_count;++i)
        if (table.deliveries[i].receiver==h && table.deliveries[i].action==d->action && table.deliveries[i].axis==A)
        { fallback(duplicate); return; }
    if (table.delivery_count==std::size(table.deliveries)) { fallback(overflow); return; }
    table.deliveries[table.delivery_count++]={h,d->action,A};
    ObjectId hid{},oid{};
    if (!object_id(h,hid) || !object_id(d->generation.owner,oid)) { fallback(identity); return; }
    const unsigned axis=ai(A);
    // Per-axis layout is kept separately below: X and Y are different actions.
    static constinit thread_local std::uint64_t layouts[2]{};
    if (bank.receiver!=h || bank.owner!=d->generation.owner || bank.receiver_id!=hid || bank.owner_id!=oid ||
        (bank.generation && (d->generation.number<bank.generation || d->generation.number>bank.generation+1)) ||
        (layouts[axis] && layouts[axis]!=pair.layout))
    { bank={}; layouts[0]=layouts[1]=0; }
    bank.receiver=h; bank.owner=d->generation.owner; bank.receiver_id=hid; bank.owner_id=oid;
    bank.generation=d->generation.number; layouts[axis]=pair.layout;
    if (bank.delivered[axis]==d->generation.number) { fallback(duplicate); return; }
    float native[2]{};
    if (!read(reinterpret_cast<std::uintptr_t>(h)+0xD64,native)) { fallback(identity); return; }
    for (unsigned a=0;a<2;++a) if (!bank.known[a] && native[a]==0) bank.known[a]=true;
    if (!bank.known[1-axis])
    {
        // Establish history by observing a normal native call; never seed stick
        // history from a potentially mouse-owned nonzero cross-axis field.
        original(h,input); bank.latest[si(winner.source)][axis]=static_cast<float>(delivered.xyz[0]);
        bank.latest[1-si(winner.source)][axis]=0; bank.known[axis]=true; return;
    }
    bank.delivered[axis]=d->generation.number;
    table.delivering=true;
    Run run{}; run.dispatch=d; run.generation=d->generation; run.receiver=h; run.axis=A;
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    run.call=calls.fetch_add(1,std::memory_order_relaxed)+1;
    run.mouse=pair.values[0]; run.stick=pair.values[1];
    const bool mixed=run.mouse!=0 && run.stick!=0;
    run.logging=mixed || singles.fetch_add(1,std::memory_order_relaxed)<4;
#endif
    Scope scope(active,&run);
    Completion completion;
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    if (run.logging) record(row(begin));
#endif
    const Source order[2]{winner.source,winner.source==Source::Mouse?Source::Gamepad:Source::Mouse};
    for (auto source:order)
    {
        const auto s=si(source); const auto value=pair.values[s];
        bank.latest[s][axis]=static_cast<float>(value); // zero/release of this axis
        if (value==0) continue;
        if (!current(run) || !run.good || !ordinary(h,run.generation)) { run.good=false; break; }
        run.source=source;
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
        run.input=value;
#endif
        Value v{}; v.xyz[0]=value;
        { Samples samples(h,source,axis,value); original(h,&v); }
        if (run.outputs[s]!=1) { run.good=false; break; }
    }
    // Keep the engine's externally visible latest sample at its original winner;
    // only native branch execution sees the private source histories.
    if (!run.interrupted && provenance.matches(run.generation))
        reinterpret_cast<float*>(reinterpret_cast<std::uintptr_t>(h)+0xD64)[axis]=static_cast<float>(delivered.xyz[0]);
    bank.known[axis]=true;
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    if (run.logging) { auto e=row(finish,run.good?ok:changed); e.flags=(run.outputs[0]&255)|((run.outputs[1]&255)<<8); record(e); }
#endif
    if (!current(run) || !run.good) bank={};
    // The common nonzero side effect executes once, after native contributions,
    // with subcall context masked. It is never replayed for the second source.
    if (run.tail) { Scope mask(active,static_cast<Run*>(nullptr)); reinterpret_cast<void (*)(void*)>(base+0x4898A70)(h); }
    completion.done=true;
}
template <Axis A> void clear(void* h)
{
    if (bank.receiver==h) { const auto a=ai(A); bank.latest[0][a]=bank.latest[1][a]=0; bank.known[a]=true; }
    reinterpret_cast<void (*)(void*)>(base+(A==Axis::X?0x489DB80:0x488A970))(h);
}
} // namespace camera_composition
