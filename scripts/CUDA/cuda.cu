#include <iostream>
#include <cuda_runtime.h>

// CUDA kernel function: each thread squares one element
__global__ void square(float *d_out, float *d_in, int n) {
    int idx = threadIdx.x + blockDim.x * blockIdx.x;
    if (idx < n) {
        d_out[idx] = d_in[idx] * d_in[idx];
    }
}

int main() {
    const int N = 16;
    size_t size = N * sizeof(float);

    // Host arrays
    float h_in[N], h_out[N];
    for (int i = 0; i < N; i++) h_in[i] = float(i);

    // Device arrays
    float *d_in, *d_out;
    cudaMalloc(&d_in, size);
    cudaMalloc(&d_out, size);

    // Copy data to device
    cudaMemcpy(d_in, h_in, size, cudaMemcpyHostToDevice);

    // Launch kernel: <<<number of blocks, threads per block>>>
    int threadsPerBlock = 8;
    int blocks = (N + threadsPerBlock - 1) / threadsPerBlock;
    square<<<blocks, threadsPerBlock>>>(d_out, d_in, N);

    // Copy results back
    cudaMemcpy(h_out, d_out, size, cudaMemcpyDeviceToHost);

    // Print results
    for (int i = 0; i < N; i++) {
        std::cout << h_in[i] << "^2 = " << h_out[i] << std::endl;
    }

    // Free device memory
    cudaFree(d_in);
    cudaFree(d_out);
    return 0;
}
