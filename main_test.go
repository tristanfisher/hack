package main

import (
	"reflect"
	"testing"
)

func Test_logic(t *testing.T) {
	tests := []struct {
		name  string
		want  any
		want1 any
	}{
		{
			name:  "test1",
			want:  nil,
			want1: nil,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, got1 := logic()
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("logic() got = %v, want %v", got, tt.want)
			}
			if !reflect.DeepEqual(got1, tt.want1) {
				t.Errorf("logic() got1 = %v, want %v", got1, tt.want1)
			}
		})
	}
}
