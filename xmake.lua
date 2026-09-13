target("MixedInputFix")
    add_rules("ue4ss.mod")
    add_files("src/dllmain.cpp")
    add_defines("ASMJIT_STATIC")
    -- Scoped cleanup must also run during Windows structured exception unwinding.
    add_cxxflags("/EHa", {force = true})
    after_load(function(target)
        -- ue4ss.mod supplies /EHsc; use only /EHa for these scoped callbacks.
        target:set("exceptions", nil)
    end)
