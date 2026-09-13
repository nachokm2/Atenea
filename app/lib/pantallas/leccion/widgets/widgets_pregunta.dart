/// Los siete tipos de pregunta del MVP, cada uno con su widget de respuesta.
///
/// Reglas que cumplen todos (§2.7 y §P09):
///
/// - Área táctil holgada: cada opción mide al menos 56 dp de alto y hay 8 dp
///   entre opciones.
/// - Sin temporizador y sin castigo: mientras se responde no hay colores de
///   acierto ni de error.
/// - El color nunca es el único portador de significado: tras comprobar, la
///   opción correcta lleva icono y texto, no solo borde verde.
/// - El valor que se emite viaja tal cual al servidor: la clave elegida, la
///   lista ordenada, el mapa de parejas o el texto libre. Si la respuesta está
///   incompleta se emite `null` para que "Comprobar" siga deshabilitado.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/theme.dart';
import '../../../design/tokens.dart';
import '../../../navegacion/armazon.dart';
import 'texto_rico.dart';

/// Cómo se pinta una opción según la fase de la pregunta.
enum _Marca { neutra, elegida, correcta, fallida }

/// Widget de respuesta para cualquier [Pregunta] del contrato.
class VistaPregunta extends StatefulWidget {
  const VistaPregunta({
    required this.pregunta,
    required this.alCambiar,
    super.key,
    this.valorInicial,
    this.bloqueado = false,
    this.resultado,
  });

  /// Pregunta a responder, sin clave de corrección.
  final Pregunta pregunta;

  /// Se llama con la respuesta completa, o con `null` si falta algo.
  final ValueChanged<Object?> alCambiar;

  /// Respuesta que el usuario ya había marcado en este paso.
  final Object? valorInicial;

  /// Tras comprobar, la pregunta deja de aceptar cambios.
  final bool bloqueado;

  /// Corrección del servidor, para destacar la respuesta correcta.
  final ResultadoRespuesta? resultado;

  @override
  State<VistaPregunta> createState() => _VistaPreguntaState();
}

class _VistaPreguntaState extends State<VistaPregunta> {
  String? _clave;
  List<String?> _huecos = <String?>[];
  Map<String, String> _parejas = <String, String>{};
  List<OpcionPregunta> _orden = <OpcionPregunta>[];
  final TextEditingController _texto = TextEditingController();

  @override
  void initState() {
    super.initState();
    _inicializar();
  }

  @override
  void didUpdateWidget(covariant VistaPregunta anterior) {
    super.didUpdateWidget(anterior);
    if (anterior.pregunta.id != widget.pregunta.id) _inicializar();
  }

  @override
  void dispose() {
    _texto.dispose();
    super.dispose();
  }

  void _inicializar() {
    final Pregunta p = widget.pregunta;
    final Object? inicial = widget.valorInicial;

    _clave = inicial is String ? inicial : null;
    _parejas = inicial is Map
        ? Map<String, String>.fromEntries(
            inicial.entries.map(
              (MapEntry<Object?, Object?> e) => MapEntry<String, String>(
                e.key?.toString() ?? '',
                e.value?.toString() ?? '',
              ),
            ),
          )
        : <String, String>{};

    final int total = p.huecos;
    _huecos = List<String?>.filled(total, null, growable: false);
    if (inicial is List) {
      for (int i = 0; i < total && i < inicial.length; i++) {
        _huecos[i] = inicial[i]?.toString();
      }
    } else if (inicial is String && total == 1 && p.tipo == TipoPregunta.completar) {
      _huecos[0] = inicial;
    }

    _orden = inicial is List && p.tipo == TipoPregunta.ordenar
        ? _ordenarSegun(p.opciones, inicial)
        : List<OpcionPregunta>.of(p.opciones);

    if (inicial is String && p.esAbierta) {
      _texto.text = inicial;
    } else if (p.esAbierta) {
      _texto.text = p.plantillaRespuesta ?? '';
    }

    // El orden inicial ya es una respuesta válida: se anuncia tras el primer
    // fotograma para no notificar durante la construcción.
    if (p.tipo == TipoPregunta.ordenar && _orden.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((Duration _) {
        if (!mounted || widget.bloqueado) return;
        widget.alCambiar(_orden.map((OpcionPregunta o) => o.clave).toList());
      });
    }
    if (p.esAbierta && _texto.text.trim().isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((Duration _) {
        if (!mounted || widget.bloqueado) return;
        widget.alCambiar(_texto.text);
      });
    }
  }

  static List<OpcionPregunta> _ordenarSegun(
    List<OpcionPregunta> opciones,
    List<Object?> claves,
  ) {
    final List<OpcionPregunta> pendientes = List<OpcionPregunta>.of(opciones);
    final List<OpcionPregunta> salida = <OpcionPregunta>[];
    for (final Object? clave in claves) {
      final int i = pendientes.indexWhere(
        (OpcionPregunta o) => o.clave == clave?.toString(),
      );
      if (i >= 0) salida.add(pendientes.removeAt(i));
    }
    return <OpcionPregunta>[...salida, ...pendientes];
  }

  /// Claves o textos que el servidor marcó como correctos.
  Set<String> get _correctas {
    final Object? v = widget.resultado?.respuestaCorrecta;
    if (v == null) return const <String>{};
    if (v is String) return <String>{v};
    if (v is List) {
      return v.map((Object? e) => e?.toString() ?? '').toSet();
    }
    if (v is Map) {
      return v.values.map((Object? e) => e?.toString() ?? '').toSet();
    }
    return <String>{v.toString()};
  }

  _Marca _marcaDe(OpcionPregunta opcion, bool elegida) {
    if (widget.resultado == null) {
      return elegida ? _Marca.elegida : _Marca.neutra;
    }
    final Set<String> correctas = _correctas;
    final bool esCorrecta =
        correctas.contains(opcion.clave) || correctas.contains(opcion.texto);
    if (esCorrecta) return _Marca.correcta;
    if (elegida) return _Marca.fallida;
    return _Marca.neutra;
  }

  @override
  Widget build(BuildContext context) {
    final Pregunta p = widget.pregunta;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _Enunciado(pregunta: p),
        const SizedBox(height: Espacio.md),
        switch (p.tipo) {
          TipoPregunta.opcionMultiple => _opciones(),
          TipoPregunta.verdaderoFalso => _verdaderoFalso(),
          TipoPregunta.completar => _completar(),
          TipoPregunta.relacionar => _relacionar(),
          TipoPregunta.ordenar => _ordenar(),
          TipoPregunta.respuestaCorta ||
          TipoPregunta.casoEstudio =>
            _abierta(monoespaciada: false),
          TipoPregunta.ejercicioSql ||
          TipoPregunta.ejercicioCodigo =>
            _abierta(monoespaciada: true),
        },
      ],
    );
  }

  // ---------------------------------------------------------------------
  // Selección simple y verdadero/falso
  // ---------------------------------------------------------------------

  Widget _opciones() {
    final List<OpcionPregunta> opciones = widget.pregunta.opciones;
    if (opciones.isEmpty) return const _SinOpciones();
    return Column(
      children: <Widget>[
        for (int i = 0; i < opciones.length; i++) ...<Widget>[
          if (i > 0) const SizedBox(height: Espacio.xs),
          _TarjetaOpcion(
            texto: opciones[i].texto,
            letra: String.fromCharCode(65 + i),
            marca: _marcaDe(opciones[i], _clave == opciones[i].clave),
            bloqueada: widget.bloqueado,
            alTocar: () => _elegir(opciones[i].clave),
          ),
        ],
      ],
    );
  }

  Widget _verdaderoFalso() {
    final List<OpcionPregunta> declaradas = widget.pregunta.opciones;
    final List<OpcionPregunta> opciones = declaradas.length >= 2
        ? declaradas
        : const <OpcionPregunta>[
            OpcionPregunta(clave: 'true', texto: 'Verdadero'),
            OpcionPregunta(clave: 'false', texto: 'Falso', indice: 1),
          ];
    return Column(
      children: <Widget>[
        for (int i = 0; i < opciones.length; i++) ...<Widget>[
          if (i > 0) const SizedBox(height: Espacio.xs),
          _TarjetaOpcion(
            texto: opciones[i].texto,
            icono: i == 0
                ? Icons.check_circle_outline_rounded
                : Icons.cancel_outlined,
            marca: _marcaDe(opciones[i], _clave == opciones[i].clave),
            bloqueada: widget.bloqueado,
            alTocar: () => _elegir(opciones[i].clave),
          ),
        ],
      ],
    );
  }

  void _elegir(String clave) {
    if (widget.bloqueado) return;
    setState(() => _clave = clave);
    widget.alCambiar(clave);
  }

  // ---------------------------------------------------------------------
  // Completar el hueco
  // ---------------------------------------------------------------------

  Widget _completar() {
    final Pregunta p = widget.pregunta;
    final List<OpcionPregunta> banco = p.opciones;
    final List<String?> segmentos = p.segmentos;

    final Widget frase = segmentos.isEmpty
        ? const SizedBox.shrink()
        : Padding(
            padding: const EdgeInsets.only(bottom: Espacio.md),
            child: _FraseConHuecos(
              segmentos: segmentos,
              valores: _huecos,
              bloqueada: widget.bloqueado,
              alVaciar: _vaciarHueco,
            ),
          );

    if (banco.isEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          frase,
          for (int i = 0; i < _huecos.length; i++) ...<Widget>[
            if (i > 0) const SizedBox(height: Espacio.sm),
            TextField(
              enabled: !widget.bloqueado,
              textInputAction: TextInputAction.done,
              decoration: InputDecoration(
                labelText: _huecos.length == 1 ? 'Tu respuesta' : 'Hueco ${i + 1}',
              ),
              onChanged: (String v) {
                _huecos[i] = v.trim().isEmpty ? null : v.trim();
                _emitirHuecos();
              },
            ),
          ],
        ],
      );
    }

    final Set<String> usadas = _huecos.whereType<String>().toSet();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        frase,
        if (segmentos.isEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.md),
            child: _FraseConHuecos(
              segmentos: List<String?>.filled(_huecos.length, null),
              valores: _huecos,
              bloqueada: widget.bloqueado,
              alVaciar: _vaciarHueco,
            ),
          ),
        Text(
          'Toca la palabra que completa la frase',
          style: context.textos.bodyMedium?.copyWith(
            color: context.paleta.textoSecundario,
          ),
        ),
        const SizedBox(height: Espacio.xs),
        Wrap(
          spacing: Espacio.xs,
          runSpacing: Espacio.xs,
          children: <Widget>[
            for (final OpcionPregunta o in banco)
              _FichaBanco(
                texto: o.texto,
                usada: usadas.contains(o.clave),
                bloqueada: widget.bloqueado,
                alTocar: () => _rellenar(o.clave),
              ),
          ],
        ),
      ],
    );
  }

  void _rellenar(String clave) {
    if (widget.bloqueado) return;
    final int libre = _huecos.indexWhere((String? v) => v == null);
    if (libre < 0) return;
    setState(() => _huecos[libre] = clave);
    _emitirHuecos();
  }

  void _vaciarHueco(int indice) {
    if (widget.bloqueado) return;
    setState(() => _huecos[indice] = null);
    _emitirHuecos();
  }

  void _emitirHuecos() {
    final bool completo = !_huecos.any((String? v) => v == null);
    if (!completo) {
      widget.alCambiar(null);
      return;
    }
    widget.alCambiar(
      _huecos.length == 1 ? _huecos.first : _huecos.whereType<String>().toList(),
    );
  }

  // ---------------------------------------------------------------------
  // Relacionar
  // ---------------------------------------------------------------------

  Widget _relacionar() {
    final Pregunta p = widget.pregunta;
    final List<OpcionPregunta> izquierda = p.parejas;
    final List<OpcionPregunta> candidatas = p.candidatas;
    if (izquierda.isEmpty || candidatas.isEmpty) return const _SinOpciones();

    return Column(
      children: <Widget>[
        for (int i = 0; i < izquierda.length; i++) ...<Widget>[
          if (i > 0) const SizedBox(height: Espacio.xs),
          _FilaPareja(
            izquierda: izquierda[i].texto,
            elegida: _textoDeCandidata(candidatas, _parejas[izquierda[i].clave]),
            bloqueada: widget.bloqueado,
            alTocar: () => _elegirPareja(izquierda[i], candidatas),
          ),
        ],
      ],
    );
  }

  /// Texto visible de la candidata elegida, a partir de su clave.
  static String? _textoDeCandidata(
    List<OpcionPregunta> candidatas,
    String? clave,
  ) {
    if (clave == null) return null;
    for (final OpcionPregunta c in candidatas) {
      if (c.clave == clave) return c.texto;
    }
    return clave;
  }

  Future<void> _elegirPareja(
    OpcionPregunta fila,
    List<OpcionPregunta> candidatas,
  ) async {
    if (widget.bloqueado) return;
    final String? elegida = await mostrarHoja<String>(
      context,
      constructor: (BuildContext hoja) => _HojaCandidatas(
        titulo: fila.texto,
        candidatas: candidatas,
        actual: _parejas[fila.clave],
      ),
    );
    if (elegida == null || !mounted) return;
    // Se guarda la **clave**, no el texto: el corrector compara claves.
    setState(() => _parejas[fila.clave] = elegida);
    final bool completo = widget.pregunta.parejas.every(
      (OpcionPregunta o) => _parejas.containsKey(o.clave),
    );
    widget.alCambiar(completo ? Map<String, String>.of(_parejas) : null);
  }

  // ---------------------------------------------------------------------
  // Ordenar
  // ---------------------------------------------------------------------

  Widget _ordenar() {
    if (_orden.isEmpty) return const _SinOpciones();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          'Ordena de arriba hacia abajo',
          style: context.textos.bodyMedium?.copyWith(
            color: context.paleta.textoSecundario,
          ),
        ),
        const SizedBox(height: Espacio.xs),
        ReorderableListView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          buildDefaultDragHandles: !widget.bloqueado,
          itemCount: _orden.length,
          onReorder: _reordenar,
          itemBuilder: (BuildContext contexto, int indice) {
            final OpcionPregunta o = _orden[indice];
            return Padding(
              key: ValueKey<String>('${widget.pregunta.id}:${o.clave}'),
              padding: const EdgeInsets.only(bottom: Espacio.xs),
              child: _FilaOrdenable(
                posicion: indice + 1,
                texto: o.texto,
                bloqueada: widget.bloqueado,
                alSubir: indice == 0 ? null : () => _reordenar(indice, indice - 1),
                alBajar: indice == _orden.length - 1
                    ? null
                    : () => _reordenar(indice, indice + 2),
              ),
            );
          },
        ),
      ],
    );
  }

  void _reordenar(int desde, int hasta) {
    if (widget.bloqueado) return;
    setState(() {
      final int destino = hasta > desde ? hasta - 1 : hasta;
      final OpcionPregunta movida = _orden.removeAt(desde);
      _orden.insert(destino, movida);
    });
    widget.alCambiar(_orden.map((OpcionPregunta o) => o.clave).toList());
  }

  // ---------------------------------------------------------------------
  // Respuesta abierta y ejercicio técnico
  // ---------------------------------------------------------------------

  Widget _abierta({required bool monoespaciada}) {
    final Pregunta p = widget.pregunta;
    final AteneaPalette paleta = context.paleta;
    final String? esquema = p.esquemaSql;
    final String? semilla = p.datosSemilla;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (esquema != null && esquema.isNotEmpty)
          TarjetaCodigo(codigo: esquema, titulo: 'ESQUEMA'),
        if (semilla != null && semilla.isNotEmpty)
          TarjetaCodigo(codigo: semilla, titulo: 'DATOS DE EJEMPLO'),
        if (p.rubrica.isNotEmpty) ...<Widget>[
          TarjetaAtenea(
            padding: const EdgeInsets.all(Espacio.sm),
            hijo: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  'Qué valoraremos',
                  style: context.textos.labelSmall?.copyWith(
                    color: paleta.textoSecundario,
                  ),
                ),
                const SizedBox(height: Espacio.xxs),
                for (final String criterio in p.rubrica)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Icon(
                          Icons.check_rounded,
                          size: 16,
                          color: paleta.dominio,
                        ),
                        const SizedBox(width: Espacio.xs),
                        Expanded(
                          child: Text(
                            criterio,
                            style: context.textos.bodyMedium,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: Espacio.sm),
        ],
        TextField(
          controller: _texto,
          enabled: !widget.bloqueado,
          minLines: monoespaciada ? 5 : 4,
          maxLines: monoespaciada ? 12 : 8,
          maxLength: p.maximoCaracteres,
          keyboardType: TextInputType.multiline,
          textCapitalization: monoespaciada
              ? TextCapitalization.none
              : TextCapitalization.sentences,
          style: monoespaciada ? estiloMono(context) : context.textos.bodyLarge,
          decoration: InputDecoration(
            hintText: monoespaciada
                ? 'Escribe tu consulta'
                : 'Escribe tu respuesta con tus palabras',
            alignLabelWithHint: true,
            filled: true,
            fillColor: paleta.lectura,
          ),
          onChanged: (String v) =>
              widget.alCambiar(v.trim().isEmpty ? null : v),
        ),
        if (monoespaciada)
          Text(
            'Se ejecuta en un entorno aislado: nada de lo que escribas toca '
            'datos reales.',
            style: context.textos.bodySmall?.copyWith(
              color: paleta.textoSecundario,
            ),
          ),
      ],
    );
  }
}

// -------------------------------------------------------------------------
// Piezas compartidas
// -------------------------------------------------------------------------

class _Enunciado extends StatelessWidget {
  const _Enunciado({required this.pregunta});

  final Pregunta pregunta;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final String? contexto = pregunta.contexto;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Pildora(
              texto: pregunta.tipo.etiqueta,
              icono: Icons.help_outline_rounded,
              color: p.arcano,
            ),
            const SizedBox(width: Espacio.xs),
            Pildora(texto: pregunta.dificultad.etiqueta),
          ],
        ),
        const SizedBox(height: Espacio.sm),
        Text(pregunta.enunciado, style: context.textos.headlineSmall),
        if (contexto != null && contexto.isNotEmpty) ...<Widget>[
          const SizedBox(height: Espacio.sm),
          TextoRico(
            texto: contexto,
            estilo: context.textos.bodyLarge?.copyWith(
              color: p.textoSecundario,
            ),
            lenguajePorDefecto: pregunta.lenguaje,
          ),
        ],
      ],
    );
  }
}

class _TarjetaOpcion extends StatelessWidget {
  const _TarjetaOpcion({
    required this.texto,
    required this.marca,
    required this.bloqueada,
    required this.alTocar,
    this.letra,
    this.icono,
  });

  final String texto;
  final _Marca marca;
  final bool bloqueada;
  final VoidCallback alTocar;
  final String? letra;
  final IconData? icono;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final (Color borde, Color fondo, IconData? sello, String? sufijo) =
        switch (marca) {
      _Marca.neutra => (p.borde, p.superficie, null, null),
      _Marca.elegida => (p.arcano, p.arcano.withValues(alpha: 0.10), null, null),
      _Marca.correcta => (
          p.exito,
          p.exito.withValues(alpha: 0.12),
          Icons.check_circle_rounded,
          'Correcta',
        ),
      _Marca.fallida => (
          p.advertencia,
          p.advertencia.withValues(alpha: 0.10),
          Icons.cancel_rounded,
          'Tu respuesta',
        ),
    };

    final Widget guia = sello != null
        ? Icon(sello, color: borde)
        : (icono != null
            ? Icon(
                icono,
                color: marca == _Marca.elegida ? p.arcano : p.textoSecundario,
              )
            : Container(
                width: Espacio.lg + Espacio.xxs,
                height: Espacio.lg + Espacio.xxs,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: borde, width: 1.5),
                  color: marca == _Marca.elegida
                      ? p.arcano.withValues(alpha: 0.18)
                      : Colors.transparent,
                ),
                child: Text(
                  letra ?? '',
                  style: context.textos.labelSmall?.copyWith(
                    color: marca == _Marca.neutra ? p.textoSecundario : borde,
                  ),
                ),
              ));

    return Semantics(
      button: true,
      selected: marca == _Marca.elegida,
      label: sufijo == null ? texto : '$texto. $sufijo',
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: Redondeo.rTarjeta,
          onTap: bloqueada ? null : alTocar,
          child: AnimatedContainer(
            duration: Movimiento.micro,
            curve: Movimiento.estandar,
            constraints: const BoxConstraints(minHeight: 56),
            padding: const EdgeInsets.symmetric(
              horizontal: Espacio.md,
              vertical: Espacio.sm,
            ),
            decoration: BoxDecoration(
              color: fondo,
              borderRadius: Redondeo.rTarjeta,
              border: Border.all(
                color: borde,
                width: marca == _Marca.neutra ? 1 : 1.8,
              ),
            ),
            child: Row(
              children: <Widget>[
                guia,
                const SizedBox(width: Espacio.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Text(texto, style: context.textos.bodyLarge),
                      if (sufijo != null)
                        Text(
                          sufijo,
                          style: context.textos.bodySmall?.copyWith(
                            color: borde,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _FraseConHuecos extends StatelessWidget {
  const _FraseConHuecos({
    required this.segmentos,
    required this.valores,
    required this.bloqueada,
    required this.alVaciar,
  });

  final List<String?> segmentos;
  final List<String?> valores;
  final bool bloqueada;
  final ValueChanged<int> alVaciar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final List<Widget> piezas = <Widget>[];
    int hueco = 0;

    for (final String? trozo in segmentos) {
      if (trozo != null) {
        piezas.add(
          Padding(
            padding: const EdgeInsets.only(top: Espacio.xs),
            child: Text(trozo, style: context.textos.bodyLarge),
          ),
        );
        continue;
      }
      final int indice = hueco;
      final String? valor = indice < valores.length ? valores[indice] : null;
      piezas.add(
        Semantics(
          button: true,
          label: valor == null
              ? 'Hueco ${indice + 1}, vacío'
              : 'Hueco ${indice + 1}: $valor. Toca para vaciarlo',
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: Redondeo.rChip,
              onTap: bloqueada || valor == null ? null : () => alVaciar(indice),
              child: Container(
                constraints: const BoxConstraints(
                  minWidth: 72,
                  minHeight: Medida.areaTactilMin,
                ),
                alignment: Alignment.center,
                padding: const EdgeInsets.symmetric(horizontal: Espacio.sm),
                decoration: BoxDecoration(
                  color: valor == null
                      ? p.lectura
                      : p.arcano.withValues(alpha: 0.14),
                  borderRadius: Redondeo.rChip,
                  border: Border.all(
                    color: valor == null ? p.borde : p.arcano,
                    width: valor == null ? 1 : 1.6,
                  ),
                ),
                child: Text(
                  valor ?? '_____',
                  style: context.textos.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w800,
                    color: valor == null ? p.textoSecundario : p.textoPrimario,
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      hueco += 1;
    }

    return Container(
      padding: const EdgeInsets.all(Espacio.sm),
      decoration: BoxDecoration(
        color: p.lectura,
        borderRadius: Redondeo.rTarjeta,
        border: Border.all(color: p.borde),
      ),
      child: Wrap(
        spacing: Espacio.xs,
        runSpacing: Espacio.xxs,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: piezas,
      ),
    );
  }
}

class _FichaBanco extends StatelessWidget {
  const _FichaBanco({
    required this.texto,
    required this.usada,
    required this.bloqueada,
    required this.alTocar,
  });

  final String texto;
  final bool usada;
  final bool bloqueada;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: Redondeo.rChip,
        onTap: usada || bloqueada ? null : alTocar,
        child: Container(
          constraints: const BoxConstraints(minHeight: Medida.areaTactilMin),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: Espacio.md),
          decoration: BoxDecoration(
            color: usada ? p.borde.withValues(alpha: 0.35) : p.superficie,
            borderRadius: Redondeo.rChip,
            border: Border.all(color: usada ? p.borde : p.arcano),
          ),
          child: Text(
            texto,
            style: context.textos.bodyLarge?.copyWith(
              color: usada ? p.textoSecundario : p.textoPrimario,
              decoration: usada ? TextDecoration.lineThrough : null,
            ),
          ),
        ),
      ),
    );
  }
}

class _FilaPareja extends StatelessWidget {
  const _FilaPareja({
    required this.izquierda,
    required this.elegida,
    required this.bloqueada,
    required this.alTocar,
  });

  final String izquierda;
  final String? elegida;
  final bool bloqueada;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return TarjetaAtenea(
      alTocar: bloqueada ? null : alTocar,
      colorBorde: elegida == null ? null : p.arcano,
      semantica: elegida == null
          ? '$izquierda. Sin pareja. Toca para elegir'
          : '$izquierda con $elegida. Toca para cambiar',
      padding: const EdgeInsets.symmetric(
        horizontal: Espacio.md,
        vertical: Espacio.sm,
      ),
      hijo: Row(
        children: <Widget>[
          Expanded(
            child: Text(izquierda, style: context.textos.bodyLarge),
          ),
          const SizedBox(width: Espacio.xs),
          Icon(Icons.link_rounded, size: 18, color: p.textoSecundario),
          const SizedBox(width: Espacio.xs),
          Expanded(
            child: Text(
              elegida ?? 'Elegir',
              textAlign: TextAlign.end,
              style: context.textos.bodyLarge?.copyWith(
                color: elegida == null ? p.textoSecundario : p.arcano,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HojaCandidatas extends StatelessWidget {
  const _HojaCandidatas({
    required this.titulo,
    required this.candidatas,
    required this.actual,
  });

  final String titulo;

  /// Candidatas del lado derecho, con su clave: la hoja devuelve la **clave**,
  /// que es lo que compara el corrector del Reino.
  final List<OpcionPregunta> candidatas;

  /// Clave de la candidata ya elegida, si la hay.
  final String? actual;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          Espacio.md,
          Espacio.xs,
          Espacio.md,
          Espacio.lg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text('¿Con qué se relaciona?', style: context.textos.headlineSmall),
            const SizedBox(height: Espacio.xxs),
            Text(
              titulo,
              style: context.textos.bodyLarge?.copyWith(
                color: context.paleta.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.md),
            Flexible(
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: candidatas.length,
                separatorBuilder: (BuildContext contexto, int indice) =>
                    const SizedBox(height: Espacio.xs),
                itemBuilder: (BuildContext contexto, int indice) =>
                    _TarjetaOpcion(
                  texto: candidatas[indice].texto,
                  letra: String.fromCharCode(65 + indice),
                  marca: candidatas[indice].clave == actual
                      ? _Marca.elegida
                      : _Marca.neutra,
                  bloqueada: false,
                  alTocar: () =>
                      Navigator.of(context).pop(candidatas[indice].clave),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FilaOrdenable extends StatelessWidget {
  const _FilaOrdenable({
    required this.posicion,
    required this.texto,
    required this.bloqueada,
    required this.alSubir,
    required this.alBajar,
  });

  final int posicion;
  final String texto;
  final bool bloqueada;
  final VoidCallback? alSubir;
  final VoidCallback? alBajar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return TarjetaAtenea(
      padding: const EdgeInsets.fromLTRB(Espacio.sm, Espacio.xxs, Espacio.xxs, Espacio.xxs),
      semantica: 'Posición $posicion: $texto',
      hijo: Row(
        children: <Widget>[
          Container(
            width: Espacio.lg + Espacio.xxs,
            height: Espacio.lg + Espacio.xxs,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: p.arcano.withValues(alpha: 0.16),
            ),
            child: Text(
              '$posicion',
              style: Cifras.pequena(context).copyWith(color: p.arcano),
            ),
          ),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: Espacio.sm),
              child: Text(texto, style: context.textos.bodyLarge),
            ),
          ),
          IconButton(
            tooltip: 'Subir',
            onPressed: bloqueada ? null : alSubir,
            icon: const Icon(Icons.keyboard_arrow_up_rounded),
          ),
          IconButton(
            tooltip: 'Bajar',
            onPressed: bloqueada ? null : alBajar,
            icon: const Icon(Icons.keyboard_arrow_down_rounded),
          ),
        ],
      ),
    );
  }
}

class _SinOpciones extends StatelessWidget {
  const _SinOpciones();

  @override
  Widget build(BuildContext context) {
    return TarjetaAtenea(
      hijo: Row(
        children: <Widget>[
          Icon(Icons.info_outline_rounded, color: context.paleta.advertencia),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: Text(
              'Esta pregunta llegó incompleta. Repórtala y sigue adelante: no '
              'perderás tu avance.',
              style: context.textos.bodyMedium,
            ),
          ),
        ],
      ),
    );
  }
}
