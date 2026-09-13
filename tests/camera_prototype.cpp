#define MIXED_INPUT_FIX_TEST
#include "../src/dllmain.cpp"
#include <cassert>
#include <cmath>
#include <fstream>
#include <limits>
using namespace mixed_input;
using namespace asmjit::x86;
namespace cp = mixed_input::camera_composition;
namespace
{
template <typename T> void put(std::uintptr_t p, T v) { std::memcpy(reinterpret_cast<void*>(p),&v,sizeof(v)); }
template <typename T> T get(std::uintptr_t p) { T v{}; std::memcpy(&v,reinterpret_cast<void*>(p),sizeof(v)); return v; }
template <std::size_t N> struct Blob
{
    alignas(16) std::uint8_t data[N]{};
    std::uintptr_t p() { return reinterpret_cast<std::uintptr_t>(data); }
};
Blob<0x1200> controller, settings, character;
Blob<0x900> owner;
Blob<0x200> config, manager, common;
Blob<0x100> actions[2], instances[2];
Blob<0x1E0> maps;
Blob<0x200> mapping_stack;
Blob<0x1000> evaluation_stack;
Blob<0x2000> chunks;
Blob<0x100> cvar;
std::uintptr_t vtable[0xE00/8]{};
std::uintptr_t frame{};
unsigned tail_calls{}, modifier_calls{}, negate_calls{};
bool nested_reset{}, throw_tail{}, unhook_output{};
Installation* installed{};
void* config_get() { return config.data; }
void* character_get() { return character.data; }
void* world_get() { return settings.data; }
void* common_get() { return common.data; }
void* null_get() { return nullptr; }
std::uint8_t false_get() { return 0; }
float scale(void*, float x) { return x; }
void init_soft(void* out) { std::memset(out,0,8); }
void no_op() {}
void common_tail(void*) { ++tail_calls; if (throw_tail) throw 17; }
void modifier_execute(void*, void*, void* params)
{
    ++modifier_calls;
    auto v=get<cp::Value>(reinterpret_cast<std::uintptr_t>(params)+8);
    v.xyz[0]*=0.28;
    put(reinterpret_cast<std::uintptr_t>(params)+0x30,v);
}
void negate_execute(void* object, void*, void* params)
{
    ++negate_calls;
    auto in=get<cp::Value>(reinterpret_cast<std::uintptr_t>(params)+8); cp::Value out{};
    // Dispatch to the exact extracted native Negate body through the shipping
    // modifier runner's reflected-call boundary; no hand-written sign transform.
    reinterpret_cast<cp::Modifier>(base+0x3933800)(object,&out,owner.data,&in,0.016f);
    put(reinterpret_cast<std::uintptr_t>(params)+0x30,out);
}
void* modifier_lookup() { return reinterpret_cast<void*>(1); }
// Called from shipping native add, so disable/unwind occurs inside the output observer.
void* add_config_get()
{
    if (nested_reset) { nested_reset=false; provenance.reset(owner.data,frame); }
    if (unhook_output) { unhook_output=false; assert(installed->commit(false)); }
    return config.data;
}
void stub(std::uintptr_t rva, std::uintptr_t target)
{
    const std::uint8_t mov[]{0x48,0xB8},jump[]{0xFF,0xE0};
    std::memcpy(reinterpret_cast<void*>(base+rva),mov,2); put(base+rva+2,target);
    std::memcpy(reinterpret_cast<void*>(base+rva+10),jump,2);
}
void fixture()
{
    base=reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr,0x9400000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE)); assert(base);
    IMAGE_DOS_HEADER dos{}; dos.e_magic=IMAGE_DOS_SIGNATURE; dos.e_lfanew=0x100; put(base,dos);
    IMAGE_NT_HEADERS64 nt{}; nt.Signature=IMAGE_NT_SIGNATURE; nt.FileHeader.Machine=IMAGE_FILE_MACHINE_AMD64;
    nt.OptionalHeader.Magic=IMAGE_NT_OPTIONAL_HDR64_MAGIC; nt.OptionalHeader.SizeOfImage=0x9400000; put(base+0x100,nt);
    for (auto s:sites::signatures) { auto b=decode(s.hex); std::memcpy(reinterpret_cast<void*>(base+s.rva),b.data(),b.size()); }
    for (auto s:cp::signatures) { auto b=decode(s.hex); std::memcpy(reinterpret_cast<void*>(base+s.rva),b.data(),b.size()); }
    std::ifstream f("build/camera-prototype/shipping-fixture.bin",std::ios::binary); assert(f);
    std::uint32_t n{}; f.read(reinterpret_cast<char*>(&n),4);
    while (n--) { std::uint32_t rva{},len{}; f.read(reinterpret_cast<char*>(&rva),4); f.read(reinterpret_cast<char*>(&len),4);
        f.read(reinterpret_cast<char*>(base+rva),len); }
    f.read(reinterpret_cast<char*>(&n),4);
    put(cvar.p()+4,1.0f);
    while (n--) { std::uint32_t rva{}; f.read(reinterpret_cast<char*>(&rva),4); put(base+rva,cvar.p()); }
    assert(f.good());
    put(config.p()+0x110,settings.p()); put(settings.p()+0x6E4,0.02f);
    // The native Y stick branch uses +0xBD4, independently of X's +0xBCC.
    for (auto offset:{0xB98,0xB9C,0xBC8,0xBCC,0xBD4,0xC64}) put(settings.p()+offset,1.0f);
    put(controller.p()+0xD60,1.0f); put(controller.p()+0xD5C,1.0f); put(controller.p()+0x860,1.0f); put(controller.p()+0x864,1.0f);
    vtable[0x838/8]=base+0x30C8E30; vtable[0xD18/8]=base+0x3564E20; vtable[0xD10/8]=base+0x3563AB0;
    put(controller.p(),reinterpret_cast<std::uintptr_t>(vtable));
    put(base+0x92CE6D0,manager.p());
    put(base+sites::mouse_x,std::uint64_t{101}); put(base+sites::mouse_y,std::uint64_t{102});
    put(base+sites::gamepad_x,std::uint64_t{103}); put(base+sites::gamepad_y,std::uint64_t{104});
    put(base+sites::left_x,std::uint64_t{105}); put(base+sites::left_y,std::uint64_t{106});
    put(base+0x9112A84,4); put(base+0x9112A70,chunks.p()); put(chunks.p(),chunks.p()+0x100);
    unsigned idx=0;
    for (auto object:{controller.p(),owner.p(),actions[0].p(),actions[1].p()})
    { put(object+0xC,idx); put(chunks.p()+0x100+24*idx,object); put(chunks.p()+0x110+24*idx,int(idx+1)); ++idx; }
    put(owner.p()+0x548,maps.p()); put(owner.p()+0x550,4);
    for (unsigned i=0;i<4;++i)
    { const auto axis=i/2; put(maps.p()+i*0x50+0x20,actions[axis].p());
      put(maps.p()+i*0x50+0x28,std::uint64_t(i==0?101:i==1?103:i==2?102:104)); }
    for (unsigned i=0;i<2;++i)
    { put(actions[i].p()+0x50,std::uint8_t{1}); put(instances[i].p(),actions[i].p());
      put(instances[i].p()+0x50,std::uint8_t{1}); put(instances[i].p()+0x13,std::uint8_t{1}); }
    frame=evaluation_stack.p();
}
void stubs()
{
    for (auto rva:{0x46AD100U}) stub(rva,reinterpret_cast<std::uintptr_t>(&config_get));
    stub(0x37FF690,reinterpret_cast<std::uintptr_t>(&add_config_get));
    stub(0x2DC0350,reinterpret_cast<std::uintptr_t>(&world_get));
    stub(0x4885C50,reinterpret_cast<std::uintptr_t>(&character_get));
    for (auto rva:{0x357C370U,0x394C780U}) stub(rva,reinterpret_cast<std::uintptr_t>(&common_get));
    for (auto rva:{0x1126290U,0x10F6700U}) stub(rva,reinterpret_cast<std::uintptr_t>(&null_get));
    for (auto rva:{0xE32340U,0xE32300U,0x4830F00U}) stub(rva,reinterpret_cast<std::uintptr_t>(&false_get));
    stub(0x487E740,reinterpret_cast<std::uintptr_t>(&scale));
    stub(0xD83FE0,reinterpret_cast<std::uintptr_t>(&init_soft));
    stub(0xDE5FF0,reinterpret_cast<std::uintptr_t>(&init_soft));
    stub(0xE26500,reinterpret_cast<std::uintptr_t>(&no_op));
    stub(0x4898A70,reinterpret_cast<std::uintptr_t>(&common_tail));
    stub(0x10EFEF0,reinterpret_cast<std::uintptr_t>(&modifier_lookup));
    FlushInstructionCache(GetCurrentProcess(),nullptr,0);
}
using Capture=cp::Value* (*)(void*,cp::Value*,void*,const cp::Value*,float,std::uintptr_t,void*);
Capture capture{};
void candidate(unsigned mapping,double value,unsigned axis=2)
{
    if (axis==2) axis=mapping/2;
    const auto m=maps.p()+mapping*0x50; const auto f=mapping_stack.p()+0x80;
    put(f+0x37,frame); put(f+0x3F,base+sites::mapping_return); put(f+0x1F,m+0x28);
    put(f+0x7F,m); put(f+0x4F,actions[axis].p());
    cp::Value in{},out{}; in.xyz[0]=value;
    auto* result=capture(owner.data,&out,reinterpret_cast<void*>(m+0x10),&in,0.016f,f,instances[axis].data);
    assert(result==&out);
}
void start(double mx,double gx,double my=0,double gy=0)
{
    provenance.reset(owner.data,frame);
    candidate(0,mx); candidate(1,gx); candidate(2,my); candidate(3,gy);
}
void deliver(Axis axis,Source source,double value,bool prototype=true)
{
    const auto a=cp::ai(axis); cp::Value v{}; v.xyz[0]=value; put(instances[a].p()+0x38,v);
    provenance.record(provenance.generation,actions[a].data,instances[a].data,{source,axis});
    Dispatch d{provenance.generation,actions[a].data,instances[a].data,{source,axis}};
    Scope scope(current_dispatch,&d);
    if (prototype) reinterpret_cast<cp::Handler>(installed->bridges.at(axis==Axis::X?0x1200:0x1300))(controller.data,&v);
    else reinterpret_cast<cp::Handler>(base+(axis==Axis::X?sites::camera_x:sites::camera_y))(controller.data,&v);
}
void reset_camera()
{
    cp::bank={}; tail_calls=0;
    put(controller.p()+0x528,0.0); put(controller.p()+0x530,0.0);
    put(controller.p()+0xD64,0.0f); put(controller.p()+0xD68,0.0f);
    put(controller.p()+0xD60,1.0f); put(controller.p()+0xD5C,1.0f);
}
double yaw() { return get<double>(controller.p()+0x530); }
bool close_value(double a,double b) { return std::abs(a-b)<1e-6; }
void inventory_diagnostics(double mouse)
{
    using R=cp::InventoryReason;
    auto check_inventory=[&](R expected, auto mutate, auto restore) {
        start(2,-.5);
        Dispatch d{provenance.generation,actions[0].data,instances[0].data,{Source::Mouse,Axis::X}};
        mutate(d); cp::Pair pair{};
        assert(!cp::inventory(d,Axis::X,pair));
        assert(pair.diagnostic.subreason==static_cast<unsigned>(expected));
        assert(pair.diagnostic.candidate_count==cp::table.count);
        restore();
        return pair.diagnostic;
    };
    const auto noop=[]{};
    auto e=check_inventory(R::maps_read,[&](auto& d){ d.generation.owner=nullptr; },noop);
    assert(!(e.read_mask&1));
    check_inventory(R::maps_null,[&](auto&){ put(owner.p()+0x548,std::uintptr_t{}); },
        [&]{put(owner.p()+0x548,maps.p());});
    for (int count:{-1,1025})
    {
        e=check_inventory(count<0?R::count_negative:R::count_limit,[&](auto&){put(owner.p()+0x550,count);},
            [&]{put(owner.p()+0x550,4);});
        assert(e.count==count && e.maps==maps.p());
    }
    e=check_inventory(R::action_read,[&](auto&){put(owner.p()+0x548,std::uintptr_t{1});},
        [&]{put(owner.p()+0x548,maps.p());});
    assert(e.mapping==1 && e.mapping_index==0 && !(e.read_mask&4));
    e=check_inventory(R::source_axis,[&](auto&){put(maps.p()+0x28,std::uint64_t{102});},
        [&]{put(maps.p()+0x28,std::uint64_t{101});});
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    assert(e.source==1 && e.source_axis==2 && e.key==102 && e.mouse_x==101 && e.mouse_y==102);
    assert(e.candidate_index==0 && e.candidate_valid && e.candidate_mapping==maps.p());
#endif
    e=check_inventory(R::source_axis,[&](auto&){put(maps.p()+0x28,std::uint64_t{999});},
        [&]{put(maps.p()+0x28,std::uint64_t{101});});
    assert(e.source==0 && e.source_axis==0); // Axis guard intentionally remains first.
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    assert(e.key==999);
#endif
    e=check_inventory(R::triggers_nonempty,[&](auto&){put(maps.p()+8,1);},[&]{put(maps.p()+8,0);});
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    assert(e.trigger_count==1 && e.read_mask==0xfff && e.count==4 && e.mapping_action==actions[0].p());
#endif
    for (int count:{-1,65})
    {
        e=check_inventory(count<0?R::modifier_count_negative:R::modifier_count_limit,
            [&](auto&){put(maps.p()+0x18,count);},[&]{put(maps.p()+0x18,0);});
        assert(e.modifier_count==count);
    }
    check_inventory(R::candidate_invalid,[&](auto&){cp::table.entries[0].valid=false;},noop);
    e=check_inventory(R::candidate_instance,[&](auto&){cp::table.entries[0].instance=instances[1].data;},noop);
    assert(e.candidate_instance==instances[1].p());
    check_inventory(R::candidate_axis,[&](auto&){cp::table.entries[0].source.axis=Axis::Y;},noop);
    check_inventory(R::candidate_source,[&](auto&){cp::table.entries[0].source.source=Source::Gamepad;},noop);
    for (auto reason:{R::orphan_invalid,R::orphan_before,R::orphan_after,R::orphan_alignment})
    {
        e=check_inventory(reason,[&](auto&){auto& c=cp::table.entries[0];
            c.mapping=reason==R::orphan_after?maps.p()+0x140:reason==R::orphan_alignment?maps.p()+1:maps.p()-1;
            if (reason==R::orphan_invalid) c.valid=false;},noop);
        assert(e.mapping_index==-1 && e.mapping==0 && e.candidate_index==0 && !(e.read_mask&0xfc));
    }
    check_inventory(R::action_missing,[&](auto&){put(owner.p()+0x550,0); cp::table.count=0;},
        [&]{put(owner.p()+0x550,4);});
    // These actual camera deliveries must still call only the original winner,
    // clear history, and retain a separate first mapping predicate on both axes.
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    const auto before=cp::journal->next.load();
#endif
    for (unsigned axis=0;axis<2;++axis)
    {
        const auto key=maps.p()+axis*0xA0+0x28;
        for (unsigned repeat=0;repeat<3;++repeat)
        {
            reset_camera(); start(2,-.5,2,-.5); put(key,std::uint64_t{999});
            deliver(axis?Axis::Y:Axis::X,Source::Mouse,2);
            assert(!cp::bank.receiver && tail_calls==1);
            if (!axis) assert(close_value(yaw(),mouse));
            put(key,std::uint64_t(axis?102:101));
        }
    }
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    assert(cp::journal->next.load()==before+2);
    for (unsigned axis=0;axis<2;++axis)
    {
        const auto& r=cp::journal->records[before+axis];
        assert(r.sequence==before+axis+1 && r.event==cp::rejected && r.reason==cp::mappings && r.axis==axis+1);
        assert(r.inventory.subreason==static_cast<unsigned>(R::source_axis) && r.inventory.key==999);
        assert(r.action==actions[axis].p() && r.instance==instances[axis].p() && r.receiver==controller.p());
    }
#endif
    // A different predicate on the same axis is not suppressed by source_axis.
    reset_camera(); start(2,-.5); cp::table.entries[0].valid=false; deliver(Axis::X,Source::Mouse,2);
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    assert(close_value(yaw(),mouse) && !cp::bank.receiver && cp::journal->next.load()==before+3);
    assert(cp::journal->records[before+2].inventory.subreason==static_cast<unsigned>(R::candidate_invalid));
#endif
    assert(close_value(yaw(),mouse) && !cp::bank.receiver);
    std::puts("PASS: granular inventory predicates, unknown versus wrong-axis keys, native-only rejection fallback");
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    std::puts("PASS: inventory diagnostic payload and per-axis/subreason bounded journal");
#endif
}
void digital_bindings()
{
    using R=cp::InventoryReason;
    Blob<0x50> details[2]; Blob<0x30> negate;
    std::uintptr_t modvt[0x270/8]{}; modvt[0x268/8]=reinterpret_cast<std::uintptr_t>(&negate_execute);
    put(negate.p(),reinterpret_cast<std::uintptr_t>(modvt));
    put(negate.p()+0x28,std::uint8_t{1}); put(negate.p()+0x29,std::uint8_t{1}); put(negate.p()+0x2A,std::uint8_t{1});
    std::uintptr_t mods[]{negate.p()};
    put(owner.p()+0x550,6);
    for (unsigned a=0;a<2;++a)
    {
        const auto m=maps.p()+(4+a)*0x50;
        // Arbitrary full FNames, including Number: no NumPad identity/name dependency.
        const auto key=(std::uint64_t{3}<<32)+700+a;
        put(m+0x20,actions[a].p()); put(m+0x28,key); put(m+0x30,details[a].p());
        put(details[a].p(),key); put(details[a].p()+0x42,std::uint8_t{0});
    }
    for (unsigned a=0;a<2;++a)
    {
        const auto axis=a?Axis::Y:Axis::X; const auto m=maps.p()+(4+a)*0x50;
        const auto key=get<std::uint64_t>(m+0x28);
        auto angle=[&]{return get<double>(controller.p()+(a?0x528:0x530));};
        auto fresh=[&]{reset_camera(); start(2,-.5,2,-.5);};
        auto inspect=[&](bool accepted,R reason=R::none) {
            Dispatch d{provenance.generation,actions[a].data,instances[a].data,{Source::Mouse,axis}};
            cp::Pair pair{}; assert(cp::inventory(d,axis,pair)==accepted);
            if (!accepted) assert(pair.diagnostic.subreason==static_cast<unsigned>(reason));
            return pair;
        };
        fresh(); deliver(axis,Source::Mouse,2,false); const auto mouse=angle(); assert(mouse!=0);
        fresh(); deliver(axis,Source::Gamepad,-.5,false); const auto stick=angle(); assert(stick!=0);
        for (bool with_negate:{false,true})
        {
            put(m+0x10,with_negate?reinterpret_cast<std::uintptr_t>(mods):std::uintptr_t{});
            put(m+0x18,with_negate?1:0);
            fresh(); const auto count=negate_calls; const auto first=inspect(true);
            assert(first.values[0]==2 && first.values[1]==-.5);
            deliver(axis,Source::Mouse,2);
            assert(close_value(angle(),mouse+stick) && tail_calls==1 && negate_calls==count);
            // Active digital observations must poison even if marked valid or zero.
            for (double value:{1.,0.}) for (bool valid:{false,true})
            {
                fresh(); candidate(4+a,value,a); auto& c=cp::table.entries[cp::table.count-1];
                assert(c.action==actions[a].data && c.mapping==m && !c.valid);
                assert(c.value.xyz[0]==(with_negate?-value:value));
                c.valid=valid;
                const auto observed=negate_calls; const auto pair=inspect(false,R::digital_candidate);
                assert(pair.diagnostic.candidate_index==4 && pair.diagnostic.source==static_cast<unsigned>(Source::Digital));
                deliver(axis,Source::Mouse,2);
                assert(close_value(angle(),mouse) && tail_calls==1 && !cp::bank.receiver && negate_calls==observed);
            }
            // A gamepad winner also retains precisely its original native path.
            fresh(); candidate(4+a,1,a); deliver(axis,Source::Gamepad,-.5);
            assert(close_value(angle(),stick) && tail_calls==1 && !cp::bank.receiver);
            // The next complete generation discards the digital observation;
            // no previous sample can keep poisoning composition after release.
            start(2,-.5,2,-.5); const auto before=angle(); deliver(axis,Source::Mouse,2);
            assert(close_value(angle()-before,mouse+stick));
            start(2,0,2,0); deliver(axis,Source::Mouse,2); assert(cp::bank.latest[1][a]==0);
            reinterpret_cast<void (*)(void*)>(installed->bridges.at(a?0x1500:0x1400))(controller.data);
            assert(get<float>(controller.p()+0xD64+4*a)==0 && cp::bank.latest[0][a]==0 && cp::bank.latest[1][a]==0);
        }
        put(m+0x10,std::uintptr_t{}); put(m+0x18,0);
        // Rebinding an idle digital key still changes the complete layout hash.
        fresh(); const auto layout=inspect(true).layout;
        put(m+0x28,key+100); put(details[a].p(),key+100);
        assert(inspect(true).layout!=layout);
        put(m+0x28,key); put(details[a].p(),key);
        auto fallback=[&](auto mutate,auto restore,R reason=R::source_axis) {
            fresh(); mutate(); inspect(false,reason); deliver(axis,Source::Mouse,2);
            assert(close_value(angle(),mouse) && tail_calls==1 && !cp::bank.receiver); restore();
        };
        // Button-axis, unknown 1D/2D/3D, absent/broken/mismatched metadata reject.
        for (std::uint8_t type:{1,2,3,4})
            fallback([&]{put(details[a].p()+0x42,type);},[&]{put(details[a].p()+0x42,std::uint8_t{});});
        for (std::uintptr_t ptr:{std::uintptr_t{},std::uintptr_t{1}})
            fallback([&]{put(m+0x30,ptr);},[&]{put(m+0x30,details[a].p());});
        fallback([&]{put(details[a].p(),key^(std::uint64_t{1}<<32));},[&]{put(details[a].p(),key);});
        fallback([&]{put(m+8,1);},[&]{put(m+8,0);},R::triggers_nonempty);
        for (int n:{-1,65})
            fallback([&]{put(m+0x18,n);},[&]{put(m+0x18,0);},n<0?R::modifier_count_negative:R::modifier_count_limit);
        // Incomplete generations reject even though their digital rows are absent.
        fresh(); cp::table.bad=true; deliver(axis,Source::Mouse,2);
        assert(close_value(angle(),mouse) && !cp::bank.receiver);
        // Participation on a different action must not poison this action's pair.
        fresh(); candidate(4+(1-a),1,1-a); inspect(true); deliver(axis,Source::Mouse,2);
        assert(close_value(angle(),mouse+stick) && tail_calls==1);
    }
    for (auto rva:sites::movement) assert(get<std::uint16_t>(base+rva)==0x0F75);
    put(owner.p()+0x550,4); std::memset(maps.data+0x140,0,0xA0);
    std::puts("PASS: X/Y idle digital bindings compose, any digital candidate falls back, native Negate once, analog/composite/metadata/structural rejection, layout and release, movement bytes unchanged");
}
}
int main()
{
    fixture(); open_diagnostics();
    // Fail closed on every new site/guard before publishing anything.
    for (auto s:cp::signatures)
    { auto& byte=*reinterpret_cast<std::uint8_t*>(base+s.rva); byte^=1;
      Installation declined; assert(!declined.install() && !declined.bridges.memory); byte^=1; }
    Installation install; assert(install.install() && install.patches.size()==20); installed=&install;
    stubs();
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    assert(cp::open_journal());
#endif
    for (auto rva:sites::movement) assert(get<std::uint16_t>(base+rva)==0x0F75);
    // Harness supplies mapping RBP/RDI, then calls the real generated modifier
    // adapter. The shipping modifier runner handles its genuine five arguments.
    asmjit::JitRuntime runtime; asmjit::CodeHolder code; check(code.init(runtime.environment())); Assembler a(&code);
    a.push(rbp); a.push(rdi); a.sub(rsp,0x28);
    a.mov(rbp,qword_ptr(rsp,0x68)); a.mov(rdi,qword_ptr(rsp,0x70));
    a.movss(xmm0,dword_ptr(rsp,0x60)); a.movss(dword_ptr(rsp,0x20),xmm0);
    a.mov(rax,install.bridges.at(0x1000)); a.call(rax);
    a.add(rsp,0x28); a.pop(rdi); a.pop(rbp); a.ret(); check(runtime.add(&capture,&code));
    reset_camera(); start(2,0); deliver(Axis::X,Source::Mouse,2,false); const auto mouse=yaw(); assert(mouse!=0);
    reset_camera(); start(0,.5); deliver(Axis::X,Source::Gamepad,.5,false); const auto stick=yaw(); assert(stick!=0);
    reset_camera(); start(2,0); deliver(Axis::X,Source::Mouse,2); assert(close_value(yaw(),mouse) && tail_calls==1);
    reset_camera(); start(0,.5); deliver(Axis::X,Source::Gamepad,.5); assert(close_value(yaw(),stick) && tail_calls==1);
    reset_camera(); start(2,-.5); deliver(Axis::X,Source::Mouse,2);
    assert(close_value(yaw(),mouse-stick) && tail_calls==1);
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
    unsigned proof{};
    for (auto& r:cp::journal->records) if (r.event==cp::finish && r.flags==0x101 && r.reason==0) ++proof;
    assert(proof);
#endif
    std::puts("PASS: exact shipping mouse/stick branches and native adds; opposing pair contributes in one generation; one common tail");
    // Source zero while the other remains active, then a skipped mapping.
    start(2,0); deliver(Axis::X,Source::Mouse,2); assert(cp::bank.latest[1][0]==0);
    provenance.reset(owner.data,frame); candidate(0,2); deliver(Axis::X,Source::Mouse,2); assert(cp::bank.latest[1][0]==0);
    reinterpret_cast<void (*)(void*)>(install.bridges.at(0x1400))(controller.data);
    assert(get<float>(controller.p()+0xD64)==0 && cp::bank.latest[0][0]==0 && cp::bank.latest[1][0]==0);
    // Actual modifier runner dispatches a mutable object once per mapping.
    std::uintptr_t modvt[0x270/8]{}; modvt[0x268/8]=reinterpret_cast<std::uintptr_t>(&modifier_execute);
    auto* modobj=modvt; void* mods[]{&modobj}; put(maps.p()+0x10,reinterpret_cast<std::uintptr_t>(mods)); put(maps.p()+0x18,1);
    start(10,.5); assert(modifier_calls==1); assert(close_value(cp::table.entries[0].value.xyz[0],2.8));
    put(maps.p()+0x10,std::uintptr_t{}); put(maps.p()+0x18,0);
    // Eligibility failures execute only the original winner.
    auto fallback=[&](auto mutate,auto restore) { reset_camera(); start(2,-.5); mutate(); deliver(Axis::X,Source::Mouse,2);
        assert(close_value(yaw(),mouse)); restore(); };
    fallback([&]{put(instances[0].p()+0x30,1);},[&]{put(instances[0].p()+0x30,0);});
    fallback([&]{put(instances[0].p()+0x20,1);},[&]{put(instances[0].p()+0x20,0);});
    fallback([&]{put(maps.p()+8,1);},[&]{put(maps.p()+8,0);});
    fallback([&]{put(frame+0x558,std::uint8_t{1});},[&]{put(frame+0x558,std::uint8_t{});});
    fallback([&]{put(chunks.p()+0x110,0);},[&]{put(chunks.p()+0x110,1);});
    reset_camera(); start(2,-.5); put(manager.p()+0xDF,std::uint8_t{1}); deliver(Axis::X,Source::Mouse,2);
    assert(yaw()==0 && tail_calls==0); put(manager.p()+0xDF,std::uint8_t{});
    reset_camera(); start(2,-.5); put(controller.p()+0x32A,std::uint8_t{1}); deliver(Axis::X,Source::Mouse,2);
    assert(yaw()==0); put(controller.p()+0x32A,std::uint8_t{});
    reset_camera(); start(2,-.5); deliver(Axis::X,Source::Mouse,2); const auto first=yaw();
    deliver(Axis::X,Source::Mouse,2); assert(close_value(yaw()-first,mouse));
    // Nested reset and uninstallation suppress the extra source after primary.
    reset_camera(); start(2,-.5); nested_reset=true; deliver(Axis::X,Source::Mouse,2); assert(close_value(yaw(),mouse) && !cp::active);
    reset_camera(); start(2,-.5); throw_tail=true;
    try { deliver(Axis::X,Source::Mouse,2); assert(false); } catch(int) {}
    assert(!cp::active && !cp::bank.receiver && !current_dispatch); throw_tail=false;
    std::puts("PASS: zero/skip/clear, mapping modifier exactly once, trigger/modifier/pause/radial/ignore/lifetime gates, duplicate extension, reset and exception cleanup");
    inventory_diagnostics(mouse);
    digital_bindings();
    reset_camera(); start(2,-.5); unhook_output=true; deliver(Axis::X,Source::Mouse,2);
    assert(close_value(yaw(),mouse) && !install.installed && !cp::active);
    for (auto& p:install.patches) assert(matches(base+p.rva,p.before.data(),p.size));
    runtime.release(capture);
    std::puts("PASS: in-flight output uninstall returns at original +6; all 20 patches restored");
}
