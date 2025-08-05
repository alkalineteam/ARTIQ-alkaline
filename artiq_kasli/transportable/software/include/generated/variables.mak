ifeq ($(CPU),vexriscv-g)
TRIPLE=riscv32-unknown-linux
CPUFLAGS=-D__vexriscv__ -march=rv32g -mabi=ilp32d
CLANG=1
LLVM_TOOLS=1
endif
ifeq ($(CPU),vexriscv)
TRIPLE=riscv32-unknown-linux
CPUFLAGS=-D__vexriscv__ -march=rv32ima -mabi=ilp32
CLANG=1
LLVM_TOOLS=1
endif
MISOC_DIRECTORY=/nix/store/bmyzz9rrrmzn3qdr5jvf2w5jmrp6y513-python3.13-misoc/lib/python3.13/site-packages/misoc
BUILDINC_DIRECTORY=/home/artiq-alkaline/ARTIQ-alkaline/artiq_kasli/transportable/software/include
export BUILDINC_DIRECTORY
BOOTLOADER_DIRECTORY=/nix/store/vlk4j99zzkr85in5r0h1qq36b9250j5n-python3.13-artiq-9.0+36d7a2b.beta/lib/python3.13/site-packages/artiq/firmware/bootloader
LIBM_DIRECTORY=/nix/store/bmyzz9rrrmzn3qdr5jvf2w5jmrp6y513-python3.13-misoc/lib/python3.13/site-packages/misoc/software/libm
LIBPRINTF_DIRECTORY=/nix/store/bmyzz9rrrmzn3qdr5jvf2w5jmrp6y513-python3.13-misoc/lib/python3.13/site-packages/misoc/software/libprintf
LIBUNWIND_DIRECTORY=/nix/store/bmyzz9rrrmzn3qdr5jvf2w5jmrp6y513-python3.13-misoc/lib/python3.13/site-packages/misoc/software/libunwind
KSUPPORT_DIRECTORY=/nix/store/vlk4j99zzkr85in5r0h1qq36b9250j5n-python3.13-artiq-9.0+36d7a2b.beta/lib/python3.13/site-packages/artiq/firmware/ksupport
LIBUNWIND_DIRECTORY=/nix/store/bmyzz9rrrmzn3qdr5jvf2w5jmrp6y513-python3.13-misoc/lib/python3.13/site-packages/misoc/software/libunwind
RUNTIME_DIRECTORY=/nix/store/vlk4j99zzkr85in5r0h1qq36b9250j5n-python3.13-artiq-9.0+36d7a2b.beta/lib/python3.13/site-packages/artiq/firmware/runtime
