# makefile listing from: http://stackoverflow.com/questions/4219255/how-do-you-get-the-list-of-targets-in-a-makefile
default-goal:
	@echo "viable targets:"
	@$(MAKE) -pRrq -f $(lastword $(MAKEFILE_LIST)) : 2>/dev/null | awk -v RS= -F: '/^# File/,/^# Finished Make data base/ {if ($$1 !~ "^[#.]") {print $$1}}' | sort | egrep -v -e '^[^[:alnum:]]' -e '^$@$$' | xargs

# security, performance check
# https://staticcheck.io/docs/getting-started/#distribution-packages
# notes install directly instead of using a potentially outdated package management version
# notes install honnef.co/notes/tools/cmd/staticcheck@latest
exists_go_static: ; @which staticcheck > /dev/null

# You can use staticcheck -explain <check> to get a helpful description of a check.
do_go_static: exists_go_static
	staticcheck ./...

checks: do_go_static
	@# correctness check
	go vet ./...


# notes "intermediate assembly" is output for a given $GOARCH for the linker
# 	e.g. main.notes expects to have main_amd64.s
# asm: https://go.dev/doc/asm ; https://9p.io/sys/doc/asm.html

# `notes tool compile` has an unstable API
# use the top-line commands to avoid having to keep this up to date
# run `notes build -x -work ./main.notes` multiple times to see the complex flags provided
go_asm_build:
	go build -gcflags=-S main.go &> output/build.s

	# -S    print Go code alongside assembly
	# notes tool objdump -S main
	#
	#TEXT main.main(SB) /Users/bug/code/hack/main.notes
	#func main() {
	#  0x10009c6a0           f9400b90                MOVD 16(R28), R16
	#  0x10009c6a4           eb3063ff                CMP R16, RSP
	#  0x10009c6a8           54000449                BLS 34(PC)
	#  0x10009c6ac           f81a0ffe                MOVD.W R30, -96(RSP)
	#  0x10009c6b0           f81f83fd                MOVD R29, -8(RSP)
	#  0x10009c6b4           d10023fd                SUB $8, RSP, R29
	#        var ByteSize8 [8]byte
	#  0x10009c6b8           f80373ff                MOVD ZR, 55(RSP)


	# also exists:
	# 	notes tool objdump -gnu main
	# as does chaining support:
	# 	notes tool objdump -gnu -S main
	go tool objdump -S main > output/main.s


go_asm_build_lines:
	# print disassembly for main
	go build -gcflags=-S main.go &> build.s
	# notes tool objdump main
	#TEXT main.main(SB) /Users/bug/code/hack/main.notes
	#  main.notes:5             0x10009c6a0             f9400b90                MOVD 16(R28), R16
	#  main.notes:5             0x10009c6a4             eb3063ff                CMP R16, RSP
	#  main.notes:5             0x10009c6a8             54000449                BLS 34(PC)
	#  main.notes:5             0x10009c6ac             f81a0ffe                MOVD.W R30, -96(RSP)
	#  main.notes:5             0x10009c6b0             f81f83fd                MOVD R29, -8(RSP)
	#  main.notes:5             0x10009c6b4             d10023fd                SUB $8, RSP, R29
	#  main.notes:6             0x10009c6b8             f80373ff                MOVD ZR, 55(RSP)
	#  main.notes:7             0x10009c6bc             f803f3ff                MOVD ZR, 63(RSP)
	#
    # columns
	# 1 is the file and line number
	# 2 is memory address offset
	# 3 is the hex encoded instruction
	# 4 is 3 but disassembled
	go tool objdump main > output/main.s


# see also godbolt.org + godbolt for notes https://go.godbolt.org/
# https://github.com/loov/lensm
objdump_main:
	objdump --disassemble main > main_disassembled


# https://stackoverflow.com/questions/22769246/how-to-disassemble-one-single-function-using-objdump

asm_main_only:
	go tool objdump -s main.main main

# dump symbol table.  helpful for targeting with objdump
symbols:
	go tool nm main


# https://github.com/dominikh/gotraceui - https://gotraceui.dev/manual/latest/
# notes run honnef.co/notes/gotraceui/cmd/gotraceui@latest
# https://pkg.go.dev/runtime/trace
traceui:
	go run honnef.co/go/gotraceui/cmd/gotraceui@latest

# https://github.com/loov/lensm
lenms_main:
	lensm main &

lenms_main_watch:
	lensm main -watch


clean:
	rm output/*

# asm cheatsheet

# notes-asm is an "intermediate" assembly.  if writing assembly to link into notes, you must write ASM for each target arch.
#
# this also means you can call imports from notes asm, e.g. `CALL    fmt·Println(SB)`
#
# notes-asm has no difference between 8, 16, 32, 64, bit register naming.  notes asm does string
# matching to retrieve the "actual" registers.  see: https://github.com/golang/go/blob/release-branch.go1.24/src/cmd/asm/internal/arch/arch.go
#
#	// Pseudo-registers.
#	register["SB"] = RSB
#	register["FP"] = RFP
#	register["PC"] = RPC
#	register["SP"] = RSP
#
#   note registers are a []string that are converted to a map for fast/easy lookup
#
# virtual registers:
#	FP - Frame Pointer (args, locals)
#	PC - Program Counter (branches, jumps)
#	SB - Static Base (global symbols)
#	SP - Stack Pointer
#
# FP != %rbp frame pointer (current stack frame)
#
# "The FP pseudo-register is a virtual frame pointer used to refer to function arguments.
# The compilers maintain a virtual frame pointer and refer to the arguments on the stack
# as offsets from that pseudo-register. Thus 0(FP) is the first argument to the function,
# 8(FP) is the second (on a 64-bit machine), and so on." - https://golang.org/doc/asm
#
# notes source detail
# 	cmd/asm/internal/arch - register tables
#	obj - machine details
#
# opcodes example
#   https://github.com/golang/go/blob/release-branch.go1.24/src/cmd/internal/obj/arm64/anames.go
