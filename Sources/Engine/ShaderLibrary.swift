import SceneKit

/// GPU shaders written in the Metal Shading Language and injected into
/// SceneKit's render pipeline via shader modifiers. This is where the
/// engine talks to the graphics hardware directly.
enum ShaderLibrary {

    /// Pseudo subsurface scattering for skin: a warm fresnel term makes
    /// edges glow softly as light "passes through" thin tissue.
    static let skinSurface = """
    float3 nrmS = _surface.normal;
    float3 vdirS = _surface.view;
    float fresS = pow(1.0 - saturate(dot(nrmS, vdirS)), 3.0);
    _surface.diffuse.rgb += fresS * float3(0.10, 0.045, 0.03);
    """

    /// Wool sheen for uniforms and dresses: grazing angles catch a cool
    /// fabric highlight instead of a plastic specular.
    static let clothSurface = """
    float3 nrmC = _surface.normal;
    float3 vdirC = _surface.view;
    float sheenC = pow(1.0 - saturate(dot(nrmC, vdirC)), 2.5);
    _surface.diffuse.rgb = _surface.diffuse.rgb * (1.0 - 0.22 * sheenC) + float3(0.055, 0.055, 0.06) * sheenC;
    """

    /// Frost glitter for the square's cobblestones: tiny view-dependent
    /// sparkles, as on real packed snow under lamplight.
    static let frostSurface = """
    float3 nrmF = _surface.normal;
    float3 vdirF = _surface.view;
    float2 uvF = _surface.diffuseTexcoord * 240.0;
    float sparkF = fract(sin(dot(floor(uvF), float2(12.9898, 78.233))) * 43758.5453);
    float glintF = step(0.985, sparkF) * pow(saturate(dot(nrmF, vdirF)), 2.0);
    _surface.diffuse.rgb += glintF * 0.35;
    """

    static func applySkin(_ m: SCNMaterial) {
        m.shaderModifiers = [.surface: skinSurface]
    }

    static func applyCloth(_ m: SCNMaterial) {
        m.shaderModifiers = [.surface: clothSurface]
    }

    static func applyFrost(_ m: SCNMaterial) {
        m.shaderModifiers = [.surface: frostSurface]
    }
}
